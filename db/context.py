from db.supabase import supabase
from datetime import datetime

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
        print(f"Erreur messages: {e}")
        return []

async def save_message(conversation_id: str, tenant_id: str, role: str,
                       content: str, language: str = "fr",
                       intent: str = None, confidence: float = 1.0,
                       media_type: str = "text") -> dict:
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
        print(f"Erreur save: {e}")
        return {}

async def update_contact_language(contact_id: str, language: str):
    try:
        supabase.table("contacts")\
            .update({"language": language})\
            .eq("id", contact_id)\
            .execute()
    except:
        pass

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
            "subject": f"Escalade : {reason}"
        }).execute()
        print(f"Conversation {conversation_id} escaladée")
    except Exception as e:
        print(f"Erreur escalade: {e}")