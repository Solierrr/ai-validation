"""
Definição e compilação do grafo LangGraph para validação de certificados.

Este módulo monta a topologia da pipeline multi-agente:

    START → security_guardrail → [documento seguro?]
        ├── SIM → nr10_agent → nr35_agent → consolidation → END
        └── NÃO → consolidation → END (rejeição imediata)

O grafo é compilado uma única vez (compiled_graph) e reutilizado por todas
as requisições da API, evitando overhead de recompilação.
"""

from langgraph.graph import END, StateGraph

from src.workflow.edges import _check_security
from src.workflow.nodes.consolidation_node import consolidation_node
from src.workflow.nodes.nr10_agent_node import nr10_agent_node
from src.workflow.nodes.nr35_agent_node import nr35_agent_node
from src.workflow.nodes.security_guardrail_node import security_guardrail_node
from src.workflow.state import CertificateGraphState


def build_graph() -> StateGraph:
    """
    Constrói e compila o grafo LangGraph com todos os nós e arestas.

    Topologia:
        1. security_guardrail: Verifica se os documentos são seguros (anti-injection)
        2. nr10_agent: Valida o certificado NR-10 via LLM Vision
        3. nr35_agent: Valida o certificado NR-35 via LLM Vision
        4. consolidation: Decisão final determinística (sem LLM)

    Retorna:
        Grafo compilado pronto para execução com .ainvoke()
    """
    # Cria o grafo com o schema de estado tipado
    workflow = StateGraph(CertificateGraphState)

    # ─── Registro dos nós (cada nó é uma função que recebe/retorna state) ────
    workflow.add_node("security_guardrail", security_guardrail_node)
    workflow.add_node("nr10_agent", nr10_agent_node)
    workflow.add_node("nr35_agent", nr35_agent_node)
    workflow.add_node("consolidation", consolidation_node)

    # ─── Ponto de entrada: primeiro nó a ser executado ───────────────────────
    workflow.set_entry_point("security_guardrail")

    # ─── Aresta condicional: decide o caminho após security check ────────────
    # Se seguro: segue para NR-10 agent
    # Se inseguro: pula direto para consolidation (rejeição)
    workflow.add_conditional_edges(
        "security_guardrail",
        _check_security,
        {
            "continue": "nr10_agent",  # Caminho feliz
            "reject": "consolidation",  # Short-circuit: rejeição por segurança
        },
    )

    # ─── Arestas sequenciais: fluxo linear entre os agentes ─────────────────
    workflow.add_edge("nr10_agent", "nr35_agent")      # Após NR-10, executa NR-35
    workflow.add_edge("nr35_agent", "consolidation")   # Após NR-35, consolida resultados
    workflow.add_edge("consolidation", END)            # Consolidation encerra a pipeline

    return workflow.compile()


# ─── Instância compilada do grafo (singleton) ────────────────────────────────
# Compilado uma vez na importação do módulo e reutilizado por todas as requests.
compiled_graph = build_graph()
