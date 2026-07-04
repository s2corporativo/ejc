// ── Avatar do usuário: foto redonda com fallback em iniciais ──
// O endpoint GET /users/{id}/avatar exige Authorization, então a foto é
// carregada como blob via client `api` (baseURL /api + Bearer) e exibida
// por objectURL. Tolerante: sem `avatar_url` (ou erro) → iniciais.
import { useEffect, useState } from "react";
import api from "../lib/api";
import { cn } from "./UI";

export function userInitials(name?: string | null): string {
  return (name || "?")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

const SIZE_CLASSES = {
  sm: "h-8 w-8 text-xs",
  md: "h-9 w-9 text-xs",
  lg: "h-11 w-11 text-sm",
  xl: "h-16 w-16 text-lg",
} as const;

export default function UserAvatar({
  user,
  size = "md",
  className,
}: {
  user?: { full_name?: string | null; avatar_url?: string | null } | null;
  size?: keyof typeof SIZE_CLASSES;
  className?: string;
}) {
  const avatarPath = user?.avatar_url || null;
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!avatarPath) {
      setSrc(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .get(avatarPath, { responseType: "blob" })
      .then(({ data }) => {
        objectUrl = URL.createObjectURL(data);
        if (!cancelled) setSrc(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setSrc(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [avatarPath]);

  if (src) {
    return (
      <img
        src={src}
        alt={user?.full_name || "Usuario"}
        className={cn(
          "shrink-0 rounded-full object-cover ring-2 ring-white shadow-sm",
          SIZE_CLASSES[size],
          className,
        )}
      />
    );
  }
  return (
    <div
      role="img"
      aria-label={user?.full_name || "Usuario"}
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-primary-600 font-semibold text-white ring-2 ring-white shadow-sm",
        SIZE_CLASSES[size],
        className,
      )}
    >
      {userInitials(user?.full_name)}
    </div>
  );
}
