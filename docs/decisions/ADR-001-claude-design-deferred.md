# ADR-001 — Claude Design: Adopcion Diferida

- **Status:** accepted
- **Outcome:** deferred (re-evaluación gatillada por triggers medibles)
- **Date:** 2026-04-21
- **Decider:** Fernando Mendieta (CTO)
- **Technical author:** Antigravity (Claude Code)
- **Roadmap phase at decision:** P2 — Historical Data, Analytics & Billing

---

## Contexto

Anthropic Labs lanzo **Claude Design** el 2026-04-17 como research preview (powered by Opus 4.7).
Capacidades relevantes:

- Extraccion automatica de design system desde un codebase linkeado.
- Generacion de prototipos UI/UX (pantallas, dashboards, landings).
- Exportacion de un "handoff bundle" consumible por Claude Code (Antigravity).
- Tokens **metered aparte** del chat y de Claude Code.
- Estado de producto: **research preview, rough edges**.

Scope evaluado: **producto Quantoryn/MTP** (dashboard atleta, panel coach, billing, landing app).
Marketing social **NO** entra en el scope (descartado como caso de uso).

---

## Evidencia del codigo (al 2026-04-21)

| Dimension | Hallazgo |
|-----------|----------|
| Stack de styling | MUI v7 + Emotion + Tailwind v4 (triple stack coexistente) |
| `tailwind.config.js` | Presente pero **vacio**: `theme: { extend: {} }` — no wired a tokens |
| `tokens.css` | Presente en `frontend/src/styles/tokens.css`. Define brand, sidebar, text, buttons, charts, PWA. |
| `theme.js` (MUI) | Presente en `frontend/src/theme/theme.js`. Redefine brand, paleta, tipografia y shape. |
| **Brand color `#00D4AA`** (teal Quantoryn) | **Duplicado** en `theme.js:7` y `tokens.css:3` — doble fuente de verdad |
| Tipografias | Inter, Roboto, Helvetica, Arial (declaradas en MUI theme). Cero ocurrencias de Bebas Neue / DM Sans. |
| Componentes | 58 archivos en `frontend/src/components/` — estructura **flat**, sin subcarpeta `ui/` ni `design-system/` ni primitives reusables |
| Directorios | No existe `frontend/src/components/ui/` ni `frontend/src/design-system/` |

---

## Razones objetivas del diferimiento

1. **Fase P2 no es UI-dominante.** El roadmap actual es Historical Data + Analytics + Billing. Adoptar una herramienta que genera UI mid-fase viola `one PR = one idea` y arriesga drive-by refactors prohibidos por CONSTITUTION.
2. **Design system fragmentado.** Brand color, tipografia y tokens viven en dos sitios (`tokens.css` y `theme.js`) sin sync. Claude Design extraeria esa ambiguedad y la amplificaria en el handoff bundle.
3. **Tailwind no extrae nada utilizable.** `tailwind.config.js` tiene `extend: {}`. Una extraccion automatica de tokens omitiria la mayoria del sistema real.
4. **Sin mount point claro para componentes generados.** No existe carpeta de primitives (`ui/Button`, `ui/Card`, `ui/Input`). Los 58 componentes actuales son de dominio (Athlete*, Coach*, Workout*) y no reusables como base.
5. **Costo metered separado sin presupuesto.** Tokens aparte del chat y Claude Code generan gasto operativo adicional sin ROI medible en la fase actual.
6. **Research preview con rough edges.** Riesgo de breaking changes sin aviso; adoptar en camino critico expone al roadmap a regresiones externas.

---

## Triggers medibles de re-evaluacion

La decision se revisa cuando **cualquiera** de estas condiciones se cumple:

1. **Design system consolidado a fuente unica:** `tokens.css` se vuelve la fuente canonica, `tailwind.config.extend` lo consume, y `theme.js` se deriva de ahi. Brand color y tipografia dejan de estar duplicados.
2. **Carpeta `frontend/src/components/ui/` creada** con al menos 5 primitives (`Button`, `Card`, `Input`, `Modal`, `Badge`) desacoplados de dominio.
3. **Transicion oficial a P3** o arranque de trabajo greenfield UI-heavy (landing marketing publica, nuevo billing flow con >3 pantallas nuevas).
4. **3+ PRs consecutivos con >40% de LOC modificado en `frontend/`** — señal de que la fase paso a ser UI-dominante.
5. **Claude Design sale de research preview a GA** con pricing estable y changelog publico.

---

## Trabajo preparatorio recomendado mientras tanto

Nada de esto es obligatorio en P2 — es deuda tecnica a mano cuando surja una ventana:

- [ ] Consolidar brand color en `tokens.css` y referenciarlo desde `theme.js` (una fuente de verdad).
- [ ] Wire de Tailwind a `tokens.css` via CSS variables en `theme.extend.colors`.
- [ ] Crear `frontend/src/components/ui/` y migrar progresivamente primitives.
- [ ] Decidir consolidacion de stack: mantener MUI como principal o migrar a Tailwind + headless (Radix/shadcn). Triple stack actual (MUI + Emotion + Tailwind) es deuda.
- [ ] Documentar tipografia, spacing scale, radios y sombras en `docs/design-system.md`.

---

## Rollback

No aplica — la decision es no-adoptar. Si cambian los triggers y se adopta luego, este ADR queda historico y se crea un ADR siguiente (`ADR-00X-claude-design-adoption.md`).

---

## Referencias

- `docs/ai/CONSTITUTION.md` — v4.2 CORE, regla "one PR = one idea"
- `docs/ai/REPO_MAP.md` — stack frontend React + Vite
- `frontend/src/theme/theme.js`
- `frontend/src/styles/tokens.css`
- `frontend/tailwind.config.js`
