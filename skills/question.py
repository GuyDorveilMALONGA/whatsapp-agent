"""
skills/question.py
Répond à "le bus X est où ?" avec les signalements actifs.
Si aucun signalement → dit clairement qu'il n'y en a pas.
Jamais d'invention.
"""
from datetime import datetime, timezone
from db import queries
from agent.extractor import extract, VALID_LINES
from agent.llm_brain import generate_response
from core.context_builder import build_context


async def handle(message: str, contact: dict, langue: str,
                 history: list | None = None) -> str:
    result = extract(message)

    # Ligne inconnue — réponse directe sans LLM
    if result.ligne and not result.ligne_valide:
        valides = ", ".join(sorted(VALID_LINES)[:10])
        if langue == "wolof":
            return (f"Ligne {result.ligne} — duma ko xam. "
                    f"Lignes Dem Dikk yi : {valides}...")
        return (f"❌ La ligne *{result.ligne}* n'existe pas dans le réseau Dem Dikk.\n"
                f"Lignes disponibles : {valides}...")

    # Pas de ligne détectée
    if not result.ligne:
        if langue == "wolof":
            return "Numéro bus bi soxor ci sa message. Wax ma : 'Bus [numéro] est où ?'"
        return "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?*"

    # Cherche signalements actifs
    signalements = queries.get_signalements_actifs(result.ligne)

    # Réponse directe si signalement récent (évite le LLM pour aller vite)
    if signalements:
        s = signalements[0]
        try:
            now = datetime.now(timezone.utc)
            created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            minutes_ago = int((now - created).total_seconds() / 60)
            age = f"il y a {minutes_ago} min" if minutes_ago > 0 else "à l'instant"
        except Exception:
            age = "récemment"

        if langue == "wolof":
            return (f"🚌 Bus {result.ligne} — signalé ci *{s['arret_nom']}* "
                    f"{age}. Jël ak yëgël ! 🙏")
        return (f"🚌 Dernier signalement Bus *{result.ligne}* :\n"
                f"📍 *{s['arret_nom']}* — {age}.\n"
                f"Il devrait arriver bientôt !")

    # Aucun signalement → réponse LLM avec contexte complet
    ctx = build_context(
        message=message,
        intent="question",
        contact=contact,
        ligne=result.ligne,
        signalements=[],
        history=history,
    )
    return await generate_response(ctx, langue, history)


async def handle_liste_arrets(message: str, contact: dict, langue: str) -> str:
    """Répond à 'quels sont les arrêts de la ligne X ?'"""
    from agent.extractor import get_arrets_ligne
    result = extract(message)

    if not result.ligne or not result.ligne_valide:
        if langue == "wolof":
            return "Numéro ligne bi soxor. Wax ma ligne bi ?"
        return "Quelle ligne ? Ex : *arrêts du bus 15*"

    info = get_arrets_ligne(result.ligne)
    arrets = info.get("aller", [])
    arrets_str = " → ".join(arrets)

    if langue == "wolof":
        return f"🚌 Bus {result.ligne} ({info.get('description', '')}) :\n{arrets_str}"
    return (f"🚌 *Bus {result.ligne}* — {info.get('description', '')}\n"
            f"Arrêts : {arrets_str}")
