from db.supabase import supabase
from datetime import datetime


# ─── CONTACTS ────────────────────────────────────────────────

async def get_or_create_contact(phone: str, tenant_id: str) -> dict:
    try:
        result = supabase.table("contacts")\
            .select("*")\
            .eq("tenant_id", tenant_id)\
            .eq("phone", phone)\
            .single()\
            .execute()
        if result.data:
            supabase.table("contacts")\
                .update({"last_seen": datetime.now().isoformat()})\
                .eq("id", result.data["id"])\
                .execute()
            return result.data
    except:
        pass
    result = supabase.table("contacts").insert({
        "tenant_id": tenant_id,
        "phone": phone,
        "language": "fr",
        "profile_data": {}
    }).execute()
    return result.data[0] if result.data else {"id": None, "phone": phone, "language": "fr"}


async def update_contact_language(contact_id: str, language: str):
    try:
        supabase.table("contacts")\
            .update({"language": language})\
            .eq("id", contact_id)\
            .execute()
    except:
        pass


# ─── CONVERSATIONS ────────────────────────────────────────────

async def get_or_create_conversation(contact_id: str, tenant_id: str) -> dict:
    try:
        result = supabase.table("conversations")\
            .select("*")\
            .eq("tenant_id", tenant_id)\
            .eq("contact_id", contact_id)\
            .eq("status", "active")\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if result.data:
            return result.data[0]
    except:
        pass
    result = supabase.table("conversations").insert({
        "tenant_id": tenant_id,
        "contact_id": contact_id,
        "status": "active",
        "channel": "whatsapp"
    }).execute()
    return result.data[0]


async def escalate_conversation(conversation_id: str, tenant_id: str, reason: str):
    try:
        supabase.table("conversations")\
            .update({"status": "escalated"})\
            .eq("id", conversation_id)\
            .execute()
        supabase.table("tickets").insert({
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "status": "open",
            "priority": "high",
            "subject": f"Sëtu — Escalade : {reason}"
        }).execute()
        print(f"⚠️ Conversation {conversation_id} escaladée — raison: {reason}")
    except Exception as e:
        print(f"Erreur escalade: {e}")


# ─── MESSAGES ────────────────────────────────────────────────

async def get_recent_messages(conversation_id: str, limit: int = 10) -> list:
    try:
        result = supabase.table("messages")\
            .select("role, content, language, intent")\
            .eq("conversation_id", conversation_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        messages = result.data or []
        messages.reverse()
        return messages
    except Exception as e:
        print(f"Erreur récupération messages: {e}")
        return []


async def save_message(
    conversation_id: str,
    tenant_id: str,
    role: str,
    content: str,
    language: str = "fr",
    intent: str = None,
    confidence: float = 1.0,
    media_type: str = "text"
) -> dict:
    try:
        result = supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "role": role,
            "content": content,
            "language": language,
            "intent": intent,
            "confidence": confidence,
            "media_type": media_type
        }).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"Erreur sauvegarde message: {e}")
        return {}


# ─── SIGNALEMENTS ────────────────────────────────────────────

async def save_signalement(
    tenant_id: str,
    contact_id: str,
    ligne: str,
    position: str,
    lat: float = None,
    lng: float = None
) -> dict:
    """Enregistre un signalement de position de bus"""
    try:
        result = supabase.table("signalements").insert({
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "ligne": ligne,
            "position": position,
            "lat": lat,
            "lng": lng,
            "timestamp": datetime.now().isoformat(),
            "valide": True
        }).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"Erreur save signalement: {e}")
        return {}


async def get_derniers_signalements(ligne: str, tenant_id: str, limit: int = 3) -> list:
    """Récupère les derniers signalements d'une ligne"""
    try:
        result = supabase.table("signalements")\
            .select("*")\
            .eq("tenant_id", tenant_id)\
            .eq("ligne", ligne)\
            .eq("valide", True)\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        return result.data or []
    except Exception as e:
        print(f"Erreur get signalements: {e}")
        return []


# ─── ABONNEMENTS ─────────────────────────────────────────────

async def save_abonnement(
    tenant_id: str,
    contact_id: str,
    ligne: str,
    arret: str = "",
    heure_alerte: str = ""
) -> dict:
    """Enregistre l'abonnement d'un utilisateur à une ligne"""
    try:
        # Vérifier si abonnement existe déjà
        existing = supabase.table("abonnements")\
            .select("id")\
            .eq("tenant_id", tenant_id)\
            .eq("contact_id", contact_id)\
            .eq("ligne", ligne)\
            .execute()

        if existing.data:
            # Mettre à jour
            supabase.table("abonnements")\
                .update({"arret": arret, "heure_alerte": heure_alerte, "actif": True})\
                .eq("id", existing.data[0]["id"])\
                .execute()
            return existing.data[0]

        result = supabase.table("abonnements").insert({
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "ligne": ligne,
            "arret": arret,
            "heure_alerte": heure_alerte,
            "actif": True
        }).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"Erreur save abonnement: {e}")
        return {}


async def get_abonnes_ligne(ligne: str, tenant_id: str) -> list:
    """Récupère tous les abonnés actifs d'une ligne"""
    try:
        result = supabase.table("abonnements")\
            .select("*, contacts(phone)")\
            .eq("tenant_id", tenant_id)\
            .eq("ligne", ligne)\
            .eq("actif", True)\
            .execute()
        return result.data or []
    except Exception as e:
        print(f"Erreur get abonnés: {e}")
        return []
