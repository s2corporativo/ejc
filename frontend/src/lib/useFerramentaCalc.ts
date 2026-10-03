import { useEffect, useState } from "react";
import api from "./api";
import { mensagemErroFerramenta } from "./iaErro";
import type { FerramentaConfig } from "../pages/ramos/ramosConfig";
import {
  camposVisiveis,
  chavesObsoletas,
  paramsVisiveis,
} from "../pages/ramos/camposCondicionais";

/** Estado comum das calculadoras de caso e de ramo; exportação fica nas telas. */
export function useFerramentaCalc(f: FerramentaConfig) {
  const [vals, setVals] = useState<Record<string, any>>(() =>
    Object.fromEntries(
      f.campos
        .filter((c) => c.default !== undefined)
        .map((c) => [c.nome, c.default]),
    ),
  );
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const visiveis = camposVisiveis(f.campos, vals);

  useEffect(() => {
    const obsoletas = chavesObsoletas(f.campos, vals);
    if (!obsoletas.length) return;
    setVals((atuais) => {
      const copia = { ...atuais };
      obsoletas.forEach((nome) => delete copia[nome]);
      return copia;
    });
  }, [f.campos, vals]);

  const calcular = async () => {
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      const r = await api.get(f.endpoint, {
        params: paramsVisiveis(f.campos, vals),
      });
      setRes(r.data);
    } catch (e) {
      setErro(mensagemErroFerramenta(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (f.autoLoad) void calcular();
    // Edição dos campos não dispara requisições automáticas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.id]);

  return { vals, setVals, res, loading, erro, visiveis, calcular };
}
