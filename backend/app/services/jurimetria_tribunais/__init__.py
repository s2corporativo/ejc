"""Jurimetria dos tribunais — desfechos do TJMG a partir do DataJud (Issue #1527).

Diferente de `services/jurimetria.py`, que mede os casos do escritório
(`Case.resultado`), este pacote mede o comportamento do tribunal: como cada
comarca/vara decide cada assunto, a partir dos movimentos registrados na
API Pública do DataJud/CNJ. As duas jurimetrias coexistem, rotuladas.

Fatia 1 (esta): consulta sob demanda, limitada e cacheada; classificação de
desfecho por códigos da Tabela Processual Unificada verificados na fonte
oficial (SGT/CNJ); agregação em memória. Sem persistência e sem job — a
numeração de migration está disputada por PRs abertos (#1412, #1486, #1492)
e a persistência entra na fatia seguinte.
"""
