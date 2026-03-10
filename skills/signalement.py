"""
skills/signalement.py — V5.0
Enregistre un signalement + notifie les abonnés.

MIGRATIONS V5.0 depuis V4.2 :
  - FIX B9 : set_session() au lieu de set_context() (qui n'existait pas)
    La session post_signalement fonctionne ENFIN.
  - FIX B10 : VALID_LINES importé depuis config.settings (source unique)
  - FIX : _notify_abonnes renommé en notify_abonnes (public, appelé depuis main.py)
  - Extraction arrêt inchangée (déjà solide en V4.2)
"""
import re
import logging
from fastapi import BackgroundTasks
from db import queries
from services.whatsapp import send_message
from config.settings import VALID_LINES
from core.session_manager import set_session  # FIX B9 : import correct

logger = logging.getLogger(__name__)

_NOTIFICATION_DELAY_SEC = 0.3
_BATCH_SIZE = 50

# Prépositions de localisation
_LOCALISATION_PREP = r"(?:à|au|niveau|devant|près\s+de|derrière|ci|face\s+à|avant)"

# Pattern : "Bus X à/niveau/devant [arrêt]"
_ARRET_FROM_TEXT_PATTERN = re.compile(
    rf"(?:bus|ligne)\s+\w+\s+{_LOCALISATION_PREP}\s+(.+?)(?:\s*[.!?,]|$)",
    re.IGNORECASE
)

# Pattern alternatif : "[ligne] [arrêt]" avec préposition
_ARRET_SHORT_PATTERN = re.compile(
    rf"\d{{1,3}}[A-Z]?\s+{_LOCALISATION_PREP}\s+(.+?)(?:\s*[.!?,]|$)",
    re.IGNORECASE
)


def _extract_arret_from_text(text: str) -> str | None:
    m = _ARRET_FROM_TEXT_PATTERN.search(text)
    if m:
        return m.group(1).strip()
    m = _ARRET_SHORT_PATTERN.search(text)
    if m:
        return m.group(1).strip()
    return None


async def notify_abonnes(ligne: str, arret: str, signaleur_phone: str):
    """
    Notifie les abonnés avec délai entre chaque envoi.
    Appelé via BackgroundTasks.
    FIX V5.0 : renommé de _notify_abonnes → notify_abonnes (public).
    """
    import asyncio
    try:
        abonnes = queries.get_abonnes(ligne)
        alerte  = (
            f"🔔 Bus {ligne} signalé à *{arret}* à l'instant.\n"
            f"Communauté Xëtu 🚌"
        )
        notifies = 0
        for i, abonne in enumerate(abonnes):
            if abonne["phone"] == signaleur_phone:
                continue
            if i > 0 and i % _BATCH_SIZE == 0:
                await asyncio.sleep(1.0)
            ok = await send_message(abonne["phone"], alerte)
            if ok:
                notifies += 1
            await asyncio.sleep(_NOTIFICATION_DELAY_SEC)

        logger.info(f"[Signalement] Bus {ligne} @ {arret} → {notifies} notifié(s)")
        return notifies
    except Exception as e:
        logger.error(f"[Signalement] Erreur notification: {e}")
        return 0


async def handle(
    message: str,
    contact: dict,
    langue: str,
    entities: dict,
    background_tasks: BackgroundTasks,
    is_signalement_fort: bool = False,
) -> str:
    phone = contact["phone"]

    # ── 1. Extraction ligne ───────────────────────────────
    ligne = entities.get("ligne")

    # ── 2. Extraction arrêt — ordre de priorité strict ───
    arret = (
        entities.get("arret")
        or entities.get("position")
        or entities.get("origin")
        or _extract_arret_from_text(message)
    )

    # ── 3. Validation ligne ───────────────────────────────
    if not ligne:
        if langue == "wolof":
            return "Wax ma numéro bi — 'Bus 15 à Liberté 5' 🙏"
        return "❓ Quel numéro de bus ? Envoie : *Bus 15 à Liberté 5* 🙏"

    ligne_upper = str(ligne).upper()

    if ligne_upper not in VALID_LINES:
        valides = ", ".join(sorted(VALID_LINES, key=lambda x: (len(x), x))[:10]) + "..."
        if langue == "wolof":
            return (
                f"Bus bi {ligne} — duma ko xam ci réseau Dem Dikk yi.\n"
                f"Lignes yi ngi ci : {valides}"
            )
        return (
            f"❌ La ligne {ligne} n'existe pas dans le réseau Dem Dikk.\n"
            f"Lignes disponibles : {valides}"
        )

    ligne = ligne_upper

    # ── 4. Validation arrêt ───────────────────────────────
    if not arret:
        # FIX B9 : set_session au lieu de set_context (qui n'existait pas !)
        try:
            set_session(phone, etat="attente_arret", ligne=ligne)
        except Exception as e:
            logger.warning(f"[Signalement] Impossible de set attente_arret: {e}")

        if langue == "wolof":
            return (
                f"Bus {ligne} — arrêt bi dafa soxor.\n"
                f"Wax ma ci : 'Bus {ligne} à [arrêt bi]' 🙏"
            )
        return (
            f"🚌 Bus {ligne} reçu ! À quel arrêt exactement ?\n"
            f"Envoie : *Bus {ligne} à [nom de l'arrêt]* 🙏"
        )

    # Nettoyage minimal
    arret = arret.strip()
    if arret:
        arret = arret[0].upper() + arret[1:]

    # ── 4b. ANTI-FRAUDE (RED TEAM) ────────────────────────
    from core.anti_fraud import (
        compute_signalement_confidence, CONFIDENCE_THRESHOLD,
        check_distance_coherence, is_spam_pattern,
    )

    # Check spam pattern (>5 signalements en 10 min, ou 4+ lignes en 5 min)
    if is_spam_pattern(phone, ligne):
        logger.warning(f"[Signalement] Spam détecté {phone[-4:]}, rejeté")
        queries.penalise_spam(phone)
        if langue == "wolof":
            return f"⚠️ Yaw, boo bëggë wéer nit ñi, signal bu baax. Xaaral tuuti. 🙏"
        return f"⚠️ Tu signales beaucoup en peu de temps. Attends quelques minutes. 🙏"

    # Check cohérence distance (bus fantôme progressif)
    if not check_distance_coherence(phone, ligne, arret):
        logger.warning(f"[Signalement] Distance incohérente {phone[-4:]}, rejeté")
        queries.penalise_spam(phone)
        if langue == "wolof":
            return f"⚠️ Bus {ligne} mënul a nekk ci {arret} léggi. Dinga ko signalé ci kanam. 🙏"
        return f"⚠️ Le Bus {ligne} ne peut pas être à *{arret}* si vite. Vérifie et réessaie. 🙏"

    # Score de confiance
    confidence = compute_signalement_confidence(
        phone=phone, ligne=ligne, arret=arret,
        source="signalement_fort" if is_signalement_fort else "llm",
        has_verbe_observation=is_signalement_fort,
        has_arret_connu=bool(arret),
    )
    if confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            f"[Signalement] Confiance trop basse {phone[-4:]}: "
            f"{confidence:.2f} < {CONFIDENCE_THRESHOLD} → demande confirmation"
        )
        # Au lieu de rejeter → demander confirmation (Red Team recommandation #4)
        set_session(
            phone,
            etat="attente_confirmation_signalement",
            ligne=ligne,
            signalement={"position": arret, "ligne": ligne, "confidence": confidence},
        )
        if langue == "wolof":
            return f"🚌 Dinga signalé Bus {ligne} ci *{arret}* ?\nWax : *oui* wala *non*"
        return f"🚌 Tu signales le Bus {ligne} à *{arret}* ?\nRéponds *oui* ou *non*"

    # ── 5. Boost corroboration ────────────────────────────
    try:
        sigs_actifs = queries.get_signalements_actifs(ligne)
        corrobore   = any(
            s["position"].lower() == arret.lower()
            for s in sigs_actifs
            if s["phone"] != phone
        )
        if corrobore:
            queries.boost_corroboration(ligne, arret, phone)
            logger.info(f"[Signalement] Corroboration ligne={ligne} arret={arret}")
    except Exception as e:
        logger.warning(f"[Signalement] Erreur check corroboration: {e}")

    # ── 6. Enregistrement en base ─────────────────────────
    try:
        result = queries.save_signalement(ligne, arret, phone)
    except Exception as e:
        logger.error(f"[Signalement] Erreur save_signalement: {e}")
        return "❌ Erreur lors de l'enregistrement. Réessaie dans quelques secondes."

    # ── 7. Doublon détecté ────────────────────────────────
    if result is None:
        if langue == "wolof":
            return f"👍 Bus {ligne} ci *{arret}* — déjà signalé récemment. Jërëjëf !"
        return f"👍 Bus {ligne} à *{arret}* — déjà signalé il y a moins de 2 min. Merci quand même ! 🙏"

    # ── 8. Session post_signalement — FIX B9 ─────────────
    try:
        set_session(
            phone,
            etat="post_signalement",
            ligne=ligne,
            signalement={"position": arret, "ligne": ligne},
        )
    except Exception as e:
        logger.warning(f"[Signalement] Impossible de set post_signalement: {e}")

    # ── 9. Comptage abonnés ───────────────────────────────
    try:
        abonnes    = queries.get_abonnes(ligne)
        nb_abonnes = sum(1 for a in abonnes if a["phone"] != phone)
    except Exception:
        nb_abonnes = 0

    # ── 10. Notifications via BackgroundTasks ─────────────
    background_tasks.add_task(notify_abonnes, ligne, arret, phone)

    logger.info(
        f"[Signalement] ligne={ligne} arret={arret} phone={phone} "
        f"fort={is_signalement_fort} abonnes={nb_abonnes}"
    )

    # ── 11. Réponse ───────────────────────────────────────
    if nb_abonnes == 0:
        if langue == "wolof":
            return f"✅ Jërëjëf ! Bus {ligne} ci *{arret}* — enregistré. 🙏"
        return f"✅ Merci ! Bus {ligne} à *{arret}* enregistré. 🙏"

    if langue == "wolof":
        return (
            f"✅ Jërëjëf ! Bus {ligne} ci *{arret}* — enregistré.\n"
            f"Danga dém {nb_abonnes} nit yi 🙏"
        )
    return (
        f"✅ Merci ! Bus {ligne} à *{arret}* enregistré.\n"
        f"Tu viens d'aider *{nb_abonnes}* personne(s) 🙏"
    )