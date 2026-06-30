from app.routers.sumulas import router
from app.services.sumulas_ingestion import SUMULAS_SEED
print('OK:', len(router.routes), 'rotas,', len(SUMULAS_SEED), 'sumulas')