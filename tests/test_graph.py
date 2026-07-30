"""Testes da topologia do grafo LangGraph (src/workflow/graph.py)."""

from unittest.mock import patch

from src.workflow.graph import _check_security, build_graph, compiled_graph

INITIAL_STATE = {
    "cert_nr10_url": "https://exemplo.com/nr10.jpg",
    "cert_nr35_url": "https://exemplo.com/nr35.jpg",
    "current_date": "2026-07-15",
}


class TestSecurityRouting:
    """Função de roteamento condicional após o security guardrail."""

    def test_continues_when_safe(self):
        assert _check_security({"is_safe": True}) == "continue"

    def test_rejects_when_unsafe(self):
        assert _check_security({"is_safe": False}) == "reject"

    def test_rejects_when_flag_missing(self):
        """Ausência da flag é tratada como inseguro (fail-safe)."""
        assert _check_security({}) == "reject"


class TestCompiledGraph:
    """Instância pré-compilada usada pela API."""

    def test_graph_is_compiled_at_import(self):
        assert compiled_graph is not None

    def test_contains_all_pipeline_nodes(self):
        nodes = set(compiled_graph.get_graph().nodes)

        assert {"security_guardrail", "nr10_agent", "nr35_agent", "consolidation"} <= nodes


class TestPipelineExecution:
    """
    Execução do grafo com nós substituídos por funções fake.

    build_graph() resolve os nós a partir do namespace do módulo no momento
    da chamada, então o patch permite testar o roteamento de ponta a ponta
    sem chamar o LLM.
    """

    def _build_with_fakes(self, executed, is_safe):
        """Monta o grafo com nós fake que registram a ordem de execução."""

        def fake_guardrail(state):
            executed.append("security_guardrail")
            return {"is_safe": is_safe, "security_error_code": "SECURITY_RISK"}

        def fake_nr10(state):
            executed.append("nr10_agent")
            return {"nr10_result": {"valid": True}}

        def fake_nr35(state):
            executed.append("nr35_agent")
            return {"nr35_result": {"valid": True}}

        def fake_consolidation(state):
            executed.append("consolidation")
            return {"status": "ACCEPT" if state.get("is_safe") else "REJECTED", "reason": "ok"}

        with (
            patch("src.workflow.graph.security_guardrail_node", fake_guardrail),
            patch("src.workflow.graph.nr10_agent_node", fake_nr10),
            patch("src.workflow.graph.nr35_agent_node", fake_nr35),
            patch("src.workflow.graph.consolidation_node", fake_consolidation),
        ):
            return build_graph()

    def test_runs_all_nodes_in_order_when_safe(self):
        executed = []
        graph = self._build_with_fakes(executed, is_safe=True)

        result = graph.invoke(INITIAL_STATE)

        assert executed == [
            "security_guardrail",
            "nr10_agent",
            "nr35_agent",
            "consolidation",
        ]
        assert result["status"] == "ACCEPT"

    def test_skips_agents_when_unsafe(self):
        """Documento inseguro deve ir direto do guardrail para a consolidação."""
        executed = []
        graph = self._build_with_fakes(executed, is_safe=False)

        result = graph.invoke(INITIAL_STATE)

        assert executed == ["security_guardrail", "consolidation"]
        assert "nr10_agent" not in executed
        assert "nr35_agent" not in executed
        assert result["status"] == "REJECTED"
