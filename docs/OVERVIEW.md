<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Visão de produto

O serviço atende ao envio de certificados de profissionais e à conferência de empresas parceiras. O resultado ajuda o cliente que conduz o cadastro. Ele não cria o cadastro nem aprova automaticamente um profissional no restante da plataforma.

## Capacidades

- Ler dois certificados, um de instalações elétricas e outro de trabalho em altura.
- Avaliar a legibilidade e sinais de instruções que tentem manipular a análise.
- Extrair aluno, instituição, carga horária, data e estrutura do documento.
- Comparar os nomes presentes nos dois certificados.
- Consultar se uma empresa existe e está ativa.
- Classificar se alguma atividade da empresa é compatível com energia, engenharia, instalações ou áreas relacionadas.

## Regras implementadas

A conferência dos certificados exige aprovação de segurança e das duas análises. A consolidação reprova carga inferior a 20 horas no certificado de instalações elétricas e a 8 horas no de trabalho em altura. Datas legíveis com mais de 730 dias são reprovadas. Nomes ausentes são reprovados e a comparação deve alcançar similaridade de pelo menos 85 por cento.

Esses números são os critérios de aceitação do produto, e uma data ausente ou inválida não reprova o documento por verificação independente.

A consulta de empresa remove a pontuação do CNPJ e exige 14 dígitos, sem conferir localmente os dígitos verificadores, e reprova a empresa ausente ou sem situação ativa antes de analisar as atividades. A classificação considera a atividade principal e as secundárias.

Documento ou empresa reprovados são resultados da análise, acompanhados de justificativa. Falha de autenticação, limite de chamadas ou indisponibilidade externa pode impedir a análise e é informada separadamente.

## Relação com a plataforma

O serviço retorna o resultado ao cliente que enviou a solicitação, sem gravar uma aprovação no cadastro central, e a integração automática de validação profissional esperada por esse cadastro ainda não existe nesta versão.
