# ETF Intelligence Platform

**ETF Selection, Monitoring & Competitor Intelligence** — Jordan Scouarnec

Prototype statique destiné à montrer comment des données publiques peuvent être structurées pour préparer un comité de sélection d'ETF, surveiller les véhicules et centraliser une veille concurrentielle.

## Fonctions

- comparateur d'ETF par groupes cohérents ;
- performance, volatilité, maximum drawdown ;
- tracking error et tracking difference ;
- score transparent et modifiable ;
- alertes sur TER, encours, réplication et fraîcheur des données ;
- comparaison Yomoni, Nalo, Ramify et Goodvest ;
- génération automatique de `docs/index.html` ;
- mise à jour avec GitHub Actions ;
- cache local si Yahoo Finance est momentanément indisponible.

## Installation locale

```bash
python -m venv .venv
```

Windows :

```bash
.venv\Scripts\activate
```

Puis :

```bash
pip install -r requirements.txt
python generate_dashboard.py
```

Ouvrir ensuite `docs/index.html`.

## Publication GitHub Pages

1. Créer un dépôt public `ETF-Intelligence`.
2. Déposer tous les fichiers en conservant les dossiers.
3. Ouvrir **Settings > Pages**.
4. Sélectionner **Deploy from a branch**.
5. Choisir `main` puis `/docs`.
6. Enregistrer.

Lien attendu :

```text
https://VOTRE-PSEUDO.github.io/ETF-Intelligence/
```

## GitHub Actions

Dans **Actions**, ouvrir **Update ETF Intelligence Dashboard**, puis cliquer sur **Run workflow**. Le workflow s'exécute également chaque jour ouvré.

## Méthodologie

- Volatilité : écart-type des rendements journaliers × √252.
- Maximum drawdown : pire baisse depuis un sommet historique.
- Tracking error : écart-type annualisé du rendement ETF moins rendement benchmark.
- Tracking difference : rendement annualisé ETF moins rendement annualisé benchmark.

Les seuils sont définis au début de `generate_dashboard.py`. Ils sont purement illustratifs et ne représentent pas les critères internes de Yomoni.

## Limites importantes

- Yahoo Finance n'est pas une source institutionnelle.
- Les données peuvent être différées ou indisponibles.
- Le TER, l'encours, la réplication, le SFDR et les informations concurrentielles doivent être vérifiés manuellement.
- Les performances de concurrents ne sont pas comparées sans profil de risque, période et méthodologie identiques.
- Le projet ne constitue pas une recommandation d'investissement.

## Pitch entretien

> En lisant la fiche de poste, j'ai identifié deux besoins opérationnels : structurer les comparaisons d'ETF avant les comités de sélection et centraliser la veille concurrentielle. J'ai donc développé un prototype fondé sur des données publiques. Il compare des ETF à l'intérieur de groupes homogènes, calcule des indicateurs de risque et de réplication, puis fait remonter des alertes selon des règles transparentes et modifiables. J'ai également ajouté une grille concurrentielle datée, sans inventer d'allocations ni comparer des performances qui ne le seraient pas réellement. L'objectif n'est pas de remplacer les outils institutionnels, mais de montrer comment je structurerais et automatiserais une partie du suivi utile aux gérants.

## Vérifications avant entretien

- ouvrir le lien en navigation privée ;
- lancer manuellement le workflow ;
- connaître tracking error et tracking difference ;
- préciser que les seuils sont illustratifs ;
- montrer seulement : Overview → ETF Comparator → Alerts → Competitors.
