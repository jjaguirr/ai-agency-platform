"""
WorkflowDefinition → n8n JSON.

One renderer per backend. This one targets n8n's public API import
format — the same shape src/agents/ai_ml/n8n_schema.py validates.
Node positions are auto-laid (linear left-to-right); n8n's editor
will redraw them anyway.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .ir import WorkflowDefinition, TriggerNode, ActionNode


_POSITION_STEP = 200


class N8nRenderer:

    def render(self, wf: WorkflowDefinition) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        x = 0

        trigger_node = self._render_trigger(wf.trigger, x)
        nodes.append(trigger_node)
        x += _POSITION_STEP

        for step in wf.steps:
            nodes.append(self._render_action(step, x))
            x += _POSITION_STEP

        # Linear chain: each node connects to the next.
        connections: Dict[str, Any] = {}
        for i in range(len(nodes) - 1):
            connections[nodes[i]["name"]] = {
                "main": [[{"node": nodes[i + 1]["name"], "type": "main", "index": 0}]]
            }

        return {
            "name": wf.name,
            "nodes": nodes,
            "connections": connections,
            "active": False,
            "settings": {},
        }

    # --- Trigger ------------------------------------------------------------

    def _render_trigger(self, t: TriggerNode, x: int) -> Dict[str, Any]:
        if t.kind == "cron":
            return {
                "id": "trigger",
                "name": "Schedule",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [x, 0],
                "parameters": {
                    "rule": {"interval": [{
                        "field": "cronExpression",
                        "expression": t.config.get("expression", "0 9 * * 1"),
                    }]}
                },
            }
        if t.kind == "webhook":
            return {
                "id": "trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2.0,
                "position": [x, 0],
                "parameters": {"path": t.config.get("path", "hook")},
            }
        # manual
        return {
            "id": "trigger",
            "name": "Manual",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1.0,
            "position": [x, 0],
            "parameters": {},
        }

    # --- Actions ------------------------------------------------------------

    def _render_action(self, a: ActionNode, x: int) -> Dict[str, Any]:
        base = {
            "id": a.name.lower().replace(" ", "_"),
            "name": a.name,
            "position": [x, 0],
        }
        if a.kind == "http_request":
            return {**base,
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "parameters": {
                    "method": a.config.get("method", "GET"),
                    "url": a.config.get("url", ""),
                },
            }
        if a.kind == "email":
            return {**base,
                "type": "n8n-nodes-base.emailSend",
                "typeVersion": 2.1,
                "parameters": {
                    "toEmail": a.config.get("to", ""),
                    "fromEmail": a.config.get("from", ""),
                    "subject": a.config.get("subject", ""),
                    "emailType": "text",
                    "message": a.config.get("body", "={{ $json }}"),
                },
            }
        if a.kind == "slack":
            return {**base,
                "type": "n8n-nodes-base.slack",
                "typeVersion": 2.2,
                "parameters": {
                    "channel": a.config.get("channel", ""),
                    "text": a.config.get("text", ""),
                },
            }
        if a.kind == "code":
            return {**base,
                "type": "n8n-nodes-base.code",
                "typeVersion": 2.0,
                "parameters": {"jsCode": a.config.get("code", "return items;")},
            }
        # set
        return {**base,
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "parameters": {"mode": "manual", "fields": {"values": []}},
        }
