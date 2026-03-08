"""
skills/escalade.py
Ticket + transfert vers un humain.
"""
from db import queries


async def handle(message: str, contact: dict, langue: str,
                 conversation_id: str) -> str:
    phone = contact["phone"]

    queries.mark_conversation_escalated(conversation_id)
    queries.create_ticket(phone, motif=message[:200])

    if langue == "wolof":
        return (
            "👤 Waaw, dinaa la wéer ak benn agent Dem Dikk.\n"
            "Nangu am keureum — dinañu la joindre ci kanam. 🙏"
        )
    return (
        "👤 Compris. Je transfère ta demande à un agent Dem Dikk.\n"
        "Un conseiller te contactera prochainement. 🙏"
    )
