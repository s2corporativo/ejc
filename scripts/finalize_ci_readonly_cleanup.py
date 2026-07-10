from pathlib import Path
import re

# Backend router registration.
main = Path("backend/app/main.py")
main_text = main.read_text(encoding="utf-8-sig")
import_marker = "from app.routers import system_modules\n"
import_line = "from app.routers import module_settings\n"
if import_line not in main_text:
    if import_marker not in main_text:
        raise SystemExit("system_modules import marker not found")
    main_text = main_text.replace(import_marker, import_marker + import_line, 1)

include_marker = "app.include_router(system_modules.router, prefix=API)  # Mapa de Módulos — governança modular\n"
include_line = "app.include_router(module_settings.router, prefix=API)  # Lifecycle auditável dos módulos\n"
if include_line not in main_text:
    if include_marker not in main_text:
        raise SystemExit("system_modules include marker not found")
    main_text = main_text.replace(include_marker, include_marker + include_line, 1)
main.write_text(main_text, encoding="utf-8")

# Alembic metadata registration.
models = Path("backend/app/models/__init__.py")
models_text = models.read_text(encoding="utf-8-sig")
model_import = "from app.models.system_module_setting import SystemModuleSetting  # noqa\n"
if model_import not in models_text:
    models_text = models_text.rstrip() + "\n" + model_import
models.write_text(models_text, encoding="utf-8")

# Frontend lifecycle store, menu filter and route gate.
layout = Path("frontend/src/components/Layout.tsx")
layout_text = layout.read_text(encoding="utf-8")
marker = 'import OnboardingTour from "./OnboardingTour";\n'
additions = (
    'import ModuleLifecycleGate from "./ModuleLifecycleGate";\n'
    'import { useModuleLifecycleStore } from "../stores/moduleLifecycle";\n'
    'import { filterModulesByLifecycle } from "../lib/moduleLifecycle";\n'
)
if 'import ModuleLifecycleGate from "./ModuleLifecycleGate";\n' not in layout_text:
    if marker not in layout_text:
        raise SystemExit("OnboardingTour import marker not found")
    layout_text = layout_text.replace(marker, marker + additions, 1)

user_marker = "  const user = useAuth((state) => state.user);\n"
lifecycle_state = (
    "  const lifecycleSettings = useModuleLifecycleStore(\n"
    "    (state) => state.settings,\n"
    "  );\n"
)
if lifecycle_state not in layout_text:
    if user_marker not in layout_text:
        raise SystemExit("Layout user marker not found")
    layout_text = layout_text.replace(user_marker, user_marker + lifecycle_state, 1)

old_visible = (
    "  const visible = useMemo(\n"
    "    () => getNavigationModules(user?.role),\n"
    "    [user?.role],\n"
    "  );\n"
)
new_visible = (
    "  const visible = useMemo(\n"
    "    () =>\n"
    "      filterModulesByLifecycle(\n"
    "        getNavigationModules(user?.role),\n"
    "        lifecycleSettings,\n"
    "      ),\n"
    "    [user?.role, lifecycleSettings],\n"
    "  );\n"
)
if old_visible in layout_text:
    layout_text = layout_text.replace(old_visible, new_visible, 1)
elif new_visible not in layout_text:
    raise SystemExit("Visible navigation block not found")

outlet = "<Outlet />"
wrapped = "<ModuleLifecycleGate><Outlet /></ModuleLifecycleGate>"
if wrapped not in layout_text:
    if outlet not in layout_text:
        raise SystemExit("Layout Outlet not found")
    layout_text = layout_text.replace(outlet, wrapped, 1)
layout.write_text(layout_text, encoding="utf-8")

# Replace static module inventory with audited lifecycle manager.
settings = Path("frontend/src/pages/Configuracoes.tsx")
settings_text = settings.read_text(encoding="utf-8")
import_marker = 'import NotificationPreferences from "../components/NotificationPreferences";\n'
component_import = 'import ModuleLifecycleSettings from "../components/ModuleLifecycleSettings";\n'
if component_import not in settings_text:
    if import_marker not in settings_text:
        raise SystemExit("NotificationPreferences import marker not found")
    settings_text = settings_text.replace(import_marker, import_marker + component_import, 1)

settings_text = settings_text.replace(
    'import {\n  canRoleAccessPath,\n  getModuleCatalog,\n  type ModuleStatus,\n} from "../config/moduleRegistry";\n',
    'import { canRoleAccessPath } from "../config/moduleRegistry";\n',
    1,
)
settings_text = re.sub(
    r"\nconst STATUS_LABEL: Record<ModuleStatus, string> = \{.*?\n\};\n\nconst STATUS_CLASS: Record<ModuleStatus, string> = \{.*?\n\};\n",
    "\n",
    settings_text,
    count=1,
    flags=re.DOTALL,
)
settings_text = settings_text.replace("\n  const modules = getModuleCatalog();\n", "\n", 1)

start_marker = '      {tab === "modulos" && isAdmin && (\n'
end_marker = '      {tab === "integracoes" && isAdmin && <IntegrationHealthPanel />}\n'
replacement = '      {tab === "modulos" && isAdmin && <ModuleLifecycleSettings />}\n\n'
if start_marker in settings_text:
    start = settings_text.index(start_marker)
    end = settings_text.index(end_marker, start)
    settings_text = settings_text[:start] + replacement + settings_text[end:]
elif replacement not in settings_text:
    raise SystemExit("Static module settings block not found")
settings.write_text(settings_text, encoding="utf-8")
