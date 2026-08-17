export function isSidebarNavigationCollapsed(
  desktopCollapsed: boolean,
  mobileOpen: boolean,
): boolean {
  return desktopCollapsed && !mobileOpen;
}
