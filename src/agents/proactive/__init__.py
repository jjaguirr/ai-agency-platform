"""
Proactive intelligence — the bits that let the EA reach out first.

Package layout:
  triggers   — ProactiveTrigger dataclass + Priority enum (shared currency)
  state      — Redis-backed operational metadata (cooldowns, counters, queues)
  gate       — NoiseGate: cooldown / priority-floor / quiet-hours / daily-cap
  followups  — commitment extraction from free text
  behaviors  — built-in EA-level checks (morning briefing, idle nudge)
  outbound   — OutboundRouter: WhatsApp push or notifications-queue pull
  engine     — ProactiveEngine: glues gate+router+behaviors for one customer
  heartbeat  — HeartbeatDaemon: background tick loop over the EA registry
"""
