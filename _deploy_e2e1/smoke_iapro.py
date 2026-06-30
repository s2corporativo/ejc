import asyncio
from app.services.ai_gateway import executar_tarefa_ia
from app.services.system_prompts import TarefaIA


async def main():
    # Tarefa RESUMO = provider Groq (grátis), não precisa de chave Anthropic.
    r = await executar_tarefa_ia(
        TarefaIA.RESUMO,
        "Resuma em 3 linhas: contrato de locação residencial de 30 meses, "
        "aluguel R$ 2.000, cláusula de multa de 3 aluguéis por rescisão antecipada.",
        db=None, user_id=None,
    )
    print("provider=", r["provider"], "| modelo=", r["modelo"],
          "| rascunho=", r["is_rascunho"], "| tokens=", r["tokens_usados"])
    print("conteudo[:240]=", (r["conteudo"] or "")[:240].replace("\n", " "))


asyncio.run(main())
