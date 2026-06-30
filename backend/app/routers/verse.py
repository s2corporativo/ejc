from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/verse", tags=["Versículo"])

VERSES = [
    {"ref": "Filipenses 4:13",    "text": "Tudo posso naquele que me fortalece."},
    {"ref": "Jeremias 29:11",     "text": "Pois eu sei os planos que tenho para vocês, planos de fazê-los prosperar e não de causar dano, planos de dar a vocês esperança e um futuro."},
    {"ref": "Salmos 23:1",        "text": "O Senhor é o meu pastor; nada me faltará."},
    {"ref": "Provérbios 3:5-6",   "text": "Confie no Senhor de todo o seu coração e não se apoie em seu próprio entendimento. Reconheça-o em todos os seus caminhos e ele endireitará as suas veredas."},
    {"ref": "Romanos 8:28",       "text": "Sabemos que todas as coisas cooperam para o bem daqueles que amam a Deus."},
    {"ref": "Isaías 41:10",       "text": "Não tema, pois estou com você; não se angustie, pois sou o seu Deus. Eu o fortalecerei e o ajudarei; eu o sustentarei com a minha destra justa."},
    {"ref": "Mateus 6:33",        "text": "Busquem, pois, em primeiro lugar o Reino de Deus e a sua justiça, e todas essas coisas lhes serão acrescentadas."},
    {"ref": "Salmos 37:4",        "text": "Deleite-se no Senhor, e ele atenderá aos desejos do seu coração."},
    {"ref": "2 Timóteo 1:7",      "text": "Porque Deus não nos deu espírito de covardia, mas de poder, de amor e de equilíbrio."},
    {"ref": "Salmos 46:1",        "text": "Deus é o nosso refúgio e a nossa força, socorro bem-presente nas tribulações."},
    {"ref": "Josué 1:9",          "text": "Seja forte e corajoso! Não se apavore nem desanime, pois o Senhor, o seu Deus, estará com você por onde você andar."},
    {"ref": "Isaías 40:31",       "text": "Os que esperam no Senhor renovarão as suas forças. Voarão alto como águias; correrão e não ficarão exaustos; caminharão e não se cansarão."},
    {"ref": "Salmos 121:1-2",     "text": "Elevo os meus olhos para os montes. De onde me virá o socorro? O meu socorro vem do Senhor, que fez os céus e a terra."},
    {"ref": "Provérbios 16:3",    "text": "Entregue ao Senhor tudo o que você faz, e os seus planos serão bem-sucedidos."},
    {"ref": "João 14:27",         "text": "Deixo-lhes a paz; a minha paz lhes dou. Não a dou como o mundo a dá. Não se turbe o coração de vocês, nem tenham medo."},
    {"ref": "Efésios 6:10",       "text": "Finalmente, fortaleçam-se no Senhor e no seu grande poder."},
    {"ref": "Salmos 118:24",      "text": "Este é o dia que o Senhor fez; regozijemo-nos e alegremo-nos nele."},
    {"ref": "1 Pedro 5:7",        "text": "Lancem sobre ele toda a sua ansiedade, porque ele tem cuidado de vocês."},
    {"ref": "Salmos 34:8",        "text": "Provem e vejam que o Senhor é bom; feliz aquele que nele se refugia!"},
    {"ref": "Mateus 11:28",       "text": "Venham a mim, todos os que estão cansados e sobrecarregados, e eu lhes darei descanso."},
    {"ref": "Romanos 15:13",      "text": "Que o Deus da esperança os encha de toda alegria e paz por meio da fé em Cristo."},
    {"ref": "Colossenses 3:23",   "text": "Tudo o que fizerem, façam de todo o coração, como para o Senhor, e não para os homens."},
    {"ref": "Provérbios 18:10",   "text": "O nome do Senhor é uma torre forte; o justo a ela corre e fica em segurança."},
    {"ref": "Salmos 32:8",        "text": "Eu o instruirei e o ensinarei no caminho em que deve andar; aconselharei você e terei meu olho sobre você."},
    {"ref": "Deuteronômio 31:6",  "text": "Seja forte e corajoso! Não tema nem se apavore diante deles, pois o Senhor, o seu Deus, vai com você; nunca o deixará nem o abandonará."},
    {"ref": "Gálatas 6:9",        "text": "Não nos cansemos de fazer o bem, pois, no tempo certo, colheremos uma colheita, se não desanimarmos."},
    {"ref": "Salmos 55:22",       "text": "Entregue ao Senhor os seus fardos, e ele o sustentará; jamais ele permitirá que o justo seja abalado."},
    {"ref": "Isaías 43:2",        "text": "Quando você atravessar as águas, eu estarei com você; quando atravessar os rios, eles não o submergirão."},
    {"ref": "João 16:33",         "text": "No mundo vocês terão tribulações; mas tenham ânimo! Eu venci o mundo."},
    {"ref": "Habacuque 3:19",     "text": "O Senhor Soberano é a minha força; ele faz os meus pés como os do cervo e me faz andar nas alturas."},
    {"ref": "Salmos 91:1",        "text": "Aquele que habita no esconderijo do Altíssimo e descansa à sombra do Todo-poderoso."},
    {"ref": "Provérbios 4:23",    "text": "Acima de tudo, guarde o seu coração, pois dele procedem as fontes da vida."},
    {"ref": "Filipenses 4:7",     "text": "A paz de Deus, que excede todo entendimento, guardará o coração e a mente de vocês em Cristo Jesus."},
    {"ref": "Salmos 27:1",        "text": "O Senhor é a minha luz e a minha salvação; a quem temerei?"},
    {"ref": "Efésios 3:20",       "text": "Ora, àquele que é poderoso para fazer muito mais do que tudo o que pedimos ou pensamos, de acordo com o seu poder que atua em nós."},
    {"ref": "Lamentações 3:22-23","text": "As misericórdias do Senhor nunca chegam ao fim; elas são novas a cada manhã. Grande é a sua fidelidade!"},
]

@router.get("")
async def get_verse():
    now = datetime.now()
    slot = now.hour // 8          # 0 → 00h-07h | 1 → 08h-15h | 2 → 16h-23h
    day = now.timetuple().tm_yday
    idx = (day * 3 + slot) % len(VERSES)
    v = VERSES[idx]
    return {**v, "slot": slot, "total": len(VERSES)}
