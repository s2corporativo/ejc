"use client";

import { useState } from "react";
import { Scale, Loader2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

export function AuthDialog() {
  const { authOpen, setAuthOpen, setView, setUser } = useAppStore();
  const [email, setEmail] = useState("demo@juridia.com.br");
  const [loading, setLoading] = useState(false);

  function signIn() {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setUser({ email, name: email.split("@")[0] });
      setAuthOpen(false);
      setView("app");
      toast({
        title: "Bem-vindo(a) ao JuridIA!",
        description: "Conta demo ativada. Explore a plataforma.",
      });
    }, 800);
  }

  return (
    <Dialog open={authOpen} onOpenChange={setAuthOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md">
            <Scale className="h-6 w-6" />
          </div>
          <DialogTitle className="text-center text-2xl">
            Cadastre-se e comece a usar o JuridIA
          </DialogTitle>
          <DialogDescription className="text-center">
            Teste gratuitamente. Sem cartão de crédito.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Button variant="outline" className="w-full" onClick={signIn}>
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.23 0 2.34.42 3.21 1.25l2.41-2.41C17.46 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" fill="#EA4335"/></svg>
            Continuar com Google
          </Button>
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">ou</span>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">E-mail</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="voce@escritorio.com.br"
                className="pl-9"
              />
            </div>
          </div>
          <Button className="w-full" onClick={signIn} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Entrando...
              </>
            ) : (
              "Continuar com e-mail"
            )}
          </Button>
        </div>

        <DialogFooter className="flex-col gap-2">
          <p className="text-center text-xs text-muted-foreground">
            Ao continuar, você concorda com os <a href="#" className="underline">Termos de Uso</a> e a <a href="#" className="underline">Política de Privacidade</a>.
          </p>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
