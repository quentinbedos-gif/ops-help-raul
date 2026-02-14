# Ops Help Raul - POC

Agent IA RevOps pour le canal Slack #help_raul de Skello.
Repond aux questions RevOps en s'appuyant sur une Knowledge Base Notion de 85 entrees.

## Architecture

```
Slack #help_raul  -->  Slack Bot (Socket Mode)
                            |
                            v
                    KB Retriever (Notion API)
                            |
                            v
                    Claude API (Sonnet 4.5)
                            |
                            v
                    Reponse Slack (thread)
```

## Structure du projet

```
ops-help-raul/
├── app.py              # Point d'entree - Slack Bot + mode test CLI
├── agent.py            # Orchestrateur : KB retrieval + Claude API
├── kb_retriever.py     # Module de recherche dans la KB Notion
├── prompts.py          # System prompt et templates
├── requirements.txt    # Dependances Python
├── .env.example        # Template des variables d'environnement
├── Dockerfile          # Image Docker pour le deploiement
├── docker-compose.yml  # Lancement en une commande
└── README.md           # Ce fichier
```

## Installation

### Option 1 : Docker (recommande)
```bash
cd ops-help-raul
cp .env.example .env
# Editer .env avec les cles API

# Lancer le bot
docker compose up -d

# Voir les logs
docker compose logs -f

# Arreter
docker compose down
```

### Option 2 : Python direct
```bash
cd ops-help-raul
pip install -r requirements.txt
cp .env.example .env
# Editer .env avec les cles API
```

## Configuration requise

### Anthropic
- Creer une cle API sur https://console.anthropic.com

### Slack
1. Creer une app Slack sur https://api.slack.com/apps
2. Activer Socket Mode (genere un `xapp-` token)
3. Ajouter les Bot Token Scopes :
   - `chat:write`
   - `channels:history`
   - `groups:history`
   - `channels:read`
   - `groups:read`
   - `app_mentions:read`
4. Souscrire aux events :
   - `message.channels`
   - `message.groups`
   - `app_mention`
5. Installer l'app dans le workspace
6. Inviter le bot dans la channel de test

### Notion
1. Creer une integration sur https://www.notion.so/my-integrations
2. Partager la database KB avec l'integration
3. Copier le token et l'ID de la database

## Usage

### Mode Slack Bot (production)
```bash
python app.py
```

### Mode Test CLI (developpement)
```bash
python app.py --test
```
Permet de tester les reponses sans Slack.

### Test standalone de l'agent
```bash
python agent.py "Comment convertir un lead dans Raul ?"
```

## Mecanisme de confiance

L'agent evalue chaque reponse sur 3 niveaux :

| Niveau | Condition | Comportement |
|--------|-----------|-------------|
| Haute  | KB couvre exactement le sujet | Reponse directe |
| Moyenne | KB couvre partiellement | Reponse + suggestion de verifier |
| Basse | KB ne couvre pas | Escalade vers Paul-Henri/Constantin |

## KB Notion

- **85 entrees** structurees
- **14 categories** : Quote, Billing, Lead, Opportunite, Contract Change, Churn, Pricing, Calendrier, Acces, Technique, Subscription/MRR, Attribution, Rapport, Integration
- Database ID : `9a6fb1778ff040d0a28279e32fe91ff2`

## Limites du MVP

- **Informatif uniquement** : aucune action CRM (pas de modification Salesforce/Chargebee)
- **Pas de memoire conversationnelle** : chaque question est traitee independamment (sauf contexte thread)
- **Retrieval basique** : recherche par mots-cles, pas d'embeddings semantiques
- **Pas de feedback loop** : pas de mecanisme d'amelioration continue

## Prochaines phases

- Phase 2 : Embeddings semantiques pour un meilleur retrieval
- Phase 3 : Actions CRM avec validation humaine
- Phase 4 : Feedback loop et amelioration continue
- Phase 5 : Integration Salesforce + Chargebee directe
