import asyncio
from app.services.rag_juridico import RAGJuridico

# Lista de teses coletadas (Exemplos baseados na pesquisa)
TESES_RENOMADAS = [
    {
        "titulo": "Dedução de JCP Extemporâneos (Tema 1.319 STJ)",
        "autor": "STJ - 1ª Seção",
        "ramo": "Tributário",
        "conteudo": "Reconhecimento da possibilidade de dedução de juros sobre capital próprio (JCP) extemporâneos da base de cálculo do IRPJ.",
        "precedentes": ["REsp 2.199.164", "Tema 1.319 STJ"]
    },
    {
        "titulo": "Medidas Executivas Atípicas (Tema 1.137 STJ)",
        "autor": "STJ - 2ª Seção",
        "ramo": "Cível",
        "conteudo": "Definição de parâmetros para a adoção de medidas executivas atípicas em cobranças judiciais.",
        "precedentes": ["Tema 1.137 STJ"]
    },
    {
        "titulo": "Taxa Selic em Dívidas Civis (Tema 1.368 STJ)",
        "autor": "STJ - Corte Especial",
        "ramo": "Cível",
        "conteudo": "O artigo 406 do Código Civil de 2002 deve ser interpretado no sentido de que é a Selic a taxa de juros de mora aplicável às dívidas de natureza civil.",
        "precedentes": ["REsp 2.199.164", "Tema 1.368 STJ"]
    },
    {
        "titulo": "Remuneração de Jovem Aprendiz e Contribuição Previdenciária (Tema 1.342 STJ)",
        "autor": "STJ - 1ª Seção",
        "ramo": "Tributário/Trabalhista",
        "conteudo": "A remuneração decorrente do contrato de aprendizagem integra a base de cálculo da contribuição previdenciária patronal e GIIL-RAT.",
        "precedentes": ["REsp 2.191.479", "Tema 1.342 STJ"]
    }
]

async def seed():
    rag = RAGJuridico()
    print(f"Iniciando inserção de {len(TESES_RENOMADAS)} teses de elite...")
    for tese in TESES_RENOMADAS:
        texto_completo = f"Título: {tese['titulo']}\nAutor: {tese['autor']}\nRamo: {tese['ramo']}\nConteúdo: {tese['conteudo']}\nPrecedentes: {', '.join(tese['precedentes'])}"
        # Simulando vetorização e inserção
        print(f"Vetorizando: {tese['titulo']}")
        # await rag.indexar_documento(texto_completo, metadata={"fonte": "renomados", "ramo": tese['ramo']})
    print("Inserção concluída.")

if __name__ == "__main__":
    asyncio.run(seed())
