# Quantoryn — Business Strategy
> Decisiones de negocio tomadas por Fernando Mendieta (fundador).
> Actualizado: 2026-03-23

---

## Visión del Producto

Quantoryn es un **Scientific Operating System** para organizaciones de endurance.
No es una app de fitness — es infraestructura científica para coaches y atletas.

**North Star:**
```
Coach planifica → atleta ejecuta → actividad retorna → Plan vs Real → feedback → plan se adapta
```

---

## Arquitectura de Monetización

### Modelo base: B2B (coach/org paga a Quantoryn)
- El coach es el cliente principal.
- El atleta accede gratis porque su coach ya paga.
- Quantoryn NO cobra al atleta directamente en Capa 1.

### Las 3 capas de monetización

| Capa | Quién paga | Modelo | Timeline |
|------|-----------|--------|----------|
| 1 — Org Subscription | Coach/Org | Freemium + Pro/Elite | HOY (P2) |
| 2 — Athlete Plus | Atleta (add-ons personales) | B2C opcional sobre B2B | P3 |
| 3 — AI Coach | Atleta sin coach humano | B2C standalone | P4 |

### Capa 3 — AI Coach
- Vive DENTRO de Quantoryn (no producto separado).
- Mismo codebase, mismo login, mismo PMC.
- Arquitectura: atleta pertenece a "Quantoryn AI Organization" (`is_ai_managed=True`).
- Racional: Fernando es solo, separar productos fragmentaría foco y recursos.

---

## Pricing — Decisiones Confirmadas

### Estrategia de moneda
- **Precio siempre en USD.**
- MercadoPago convierte automáticamente a moneda local (ARS, COP, CLP, etc.).
- Fernando recibe equivalente en USD → cubierto contra inflación LATAM.
- Regla: *precio en USD, pago en moneda local, fundador duerme tranquilo.*

### Plan Free — Freemium permanente (NO solo trial)
- Free existe para siempre con límite de 5 atletas.
- Racional: costo marginal ~$0 (no es Netflix, es texto en DB).
- Beneficio: adopción, boca a boca, coaches aprenden la plataforma.
- El coach Free con 5 atletas = marketing pagado con infraestructura.

### Trial de 15 días
- Nuevo coach → 15 días Pro gratis (ya construido en PR-131).
- Al vencer: baja a Free (5 atletas) — NO se bloquea todo.
- TODO técnico: ajustar comportamiento post-trial en PR futuro.

### Tabla de planes

| Plan | Precio | Atletas | PMC/Analytics | Historial | Billing atletas | Invitaciones |
|------|--------|---------|---------------|-----------|-----------------|--------------|
| **Free** | $0 | 5 | ✅ Sí | ❌ No | ❌ No | ❌ No |
| **Pro** | $29/mes | Ilimitados | ✅ Sí | ✅ Sí | ✅ Sí | ✅ Sí |
| **Elite** | $69/mes | Ilimitados | ✅ Sí | ✅ Sí + avanzado | ✅ Sí | ✅ Sí + branding |
| **Athlete Plus** | $6/mes | — | Personal AI | — | — | — |
| **AI Coach** | $15-25/mes | — | IA completa | ✅ Sí | — | — |

### El momento del upgrade (atleta #6)
- Sistema BLOQUEA agregar atleta número 6 — no solo avisa.
- Aparece modal con: qué gana en Pro + CTA directo a MercadoPago.
- "Ahora no" existe pero es secundario visualmente.
- TODO técnico: PR-142 — modal de upgrade en frontend.

### Ajuste a require_plan gates (PR-130)
- Hoy bloquean PMC/analytics en Free → CAMBIAR.
- Free debe tener PMC y analytics básicos.
- Free solo bloquea: historial largo, billing, invitaciones masivas.
- TODO técnico: PR chico post PR-141.

---

## Competitive Positioning

Competidores directos en LATAM: TrainingPeaks, Final Surge, Today's Plan.
- TrainingPeaks: $19.99/mes atleta — caro para LATAM, interfaz anticuada.
- Final Surge: free coaches, atletas pagan — modelo inverso.
- Today's Plan: elite/caro, no enfocado en LATAM.

Ventaja Quantoryn:
- MercadoPago nativo (LATAM-first)
- Freemium genuinamente útil (no demo castrada)
- Scientific OS — no app de fitness
- Multi-tenant desde el día 1

---

## Pendientes de Negocio

- [ ] Definir perfil del primer cliente real (Tema 2 — pendiente)
- [ ] Definir qué debe estar listo antes del primer cliente pagado
- [ ] Definir estrategia de diferenciación vs TrainingPeaks (Tema 3)
- [ ] Revisar require_plan gates post PR-141
- [ ] PR-142: modal de upgrade atleta #6
