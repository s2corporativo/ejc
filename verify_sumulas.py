from app.routers.sumulas import router
routes = [r.path for r in router.routes]
print("Sumulas routes:", routes)

from app.services.sumulas_ingestion import ingerir_sumulas_seed, SUMULAS_SEED
print("Seed count:", len(SUMULAS_SEED))

from app.services.conflito_interesses import verificar_conflito
print("Conflito service: OK")
