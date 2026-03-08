from groq import Groq
import os
import json

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


async def extract_signalement(text: str) -> dict:
    """
    Extrait la ligne et la position depuis un message de signalement.
    Ex: "Bus 15 à Liberté 5" → {"ligne": "15", "position": "Liberté 5"}
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Tu es un extracteur d'informations pour Sëtu, un agent transport à Dakar.
Extrait le numéro de ligne de bus et la position depuis le message.
Réponds UNIQUEMENT avec ce JSON exact :
{"ligne": "NUMERO", "position": "NOM_ARRET"}

Règles :
- ligne : juste le numéro (ex: "15", "1A", "16B") — null si pas trouvé
- position : nom de l'arrêt ou lieu (ex: "Liberté 5", "Sandaga", "Palais") — null si pas trouvé
- Si le message dit "Bus 15 à Liberté 5" → {"ligne": "15", "position": "Liberté 5"}
- Si le message dit "Le 27 vient de passer devant Auchan" → {"ligne": "27", "position": "Auchan"}
- Si le message dit "je suis dans le 10, on est à Pompiers" → {"ligne": "10", "position": "Pompiers"}
Ne réponds qu'avec le JSON, rien d'autre."""
                },
                {
                    "role": "user",
                    "content": f"Message : '{text}'"
                }
            ],
            max_tokens=50,
            temperature=0
        )
        result = json.loads(response.choices[0].message.content.strip())
        return result
    except Exception as e:
        print(f"Erreur extraction signalement: {e}")
        return {"ligne": None, "position": None}


async def extract_abonnement(text: str) -> dict:
    """
    Extrait la ligne, l'arrêt et l'heure depuis un message d'abonnement.
    Ex: "Préviens-moi pour le Bus 15 depuis Liberté 5 vers 8h"
    → {"ligne": "15", "arret": "Liberté 5", "heure": "08:00"}
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Tu es un extracteur d'informations pour Sëtu, un agent transport à Dakar.
Extrait le numéro de ligne, l'arrêt de départ et l'heure depuis le message d'abonnement.
Réponds UNIQUEMENT avec ce JSON exact :
{"ligne": "NUMERO", "arret": "NOM_ARRET", "heure": "HH:MM"}

Règles :
- ligne : numéro de ligne (ex: "15", "1A") — null si pas trouvé
- arret : arrêt de départ (ex: "Liberté 5") — "" si pas mentionné
- heure : heure souhaitée au format HH:MM (ex: "08:00") — "" si pas mentionné
Ne réponds qu'avec le JSON, rien d'autre."""
                },
                {
                    "role": "user",
                    "content": f"Message : '{text}'"
                }
            ],
            max_tokens=60,
            temperature=0
        )
        result = json.loads(response.choices[0].message.content.strip())
        return result
    except Exception as e:
        print(f"Erreur extraction abonnement: {e}")
        return {"ligne": None, "arret": "", "heure": ""}
