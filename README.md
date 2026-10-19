# Score Bourse – installation (gratuite, ~15 min, depuis ton téléphone ou PC)

## 1. Créer le dépôt
1. Crée un compte sur github.com (gratuit).
2. Bouton « + » > **New repository**, nom : `bourse`, visibilité **Public**, puis Create.
3. **Add file > Upload files** : glisse tout le contenu du zip (dossiers `docs`, `scripts`, `.github` et fichiers `config.json`, `requirements.txt`). Si `.github` n’est pas pris en compte : **Add file > Create new file**, tape `.github/workflows/update.yml` comme nom et colle le contenu du fichier.
4. Clique **Commit changes**.

## 2. Autoriser la mise à jour automatique
**Settings > Actions > General > Workflow permissions** : choisis **Read and write permissions**, puis Save.

## 3. Publier le site
**Settings > Pages** : Source = *Deploy from a branch*, Branch = `main`, dossier `/docs`, Save. Ton site sera sur `https://TON-PSEUDO.github.io/bourse/`.

## 4. Notifications gratuites (ntfy)
1. Installe l’appli **ntfy** (iOS / Android).
2. Invente un nom de sujet long et secret, ex. `bourse-x7k29qpw41`, et abonne-toi dedans dans l’appli.
3. Sur GitHub : **Settings > Secrets and variables > Actions > New repository secret**, nom `NTFY_TOPIC`, valeur = ton sujet.

## 5. Premier lancement
Onglet **Actions** > « Mise à jour des scores » > **Run workflow**. Après ~1 minute, ouvre ton site. Ensuite, mise à jour toutes les 5 min environ (GitHub peut retarder de quelques minutes) du lundi au vendredi, de 7h à 16h59 UTC, ce qui couvre la séance de Paris (9h-17h30) été comme hiver.

## Personnaliser
Modifie `config.json` (symboles Yahoo Finance : `.PA` Paris, `.DE` Allemagne, `.AS` Amsterdam…).
Tu reçois une notification quand le verdict d’une action change (ex. Surveiller -> Acheter).

## Fréquence
Dans `.github/workflows/update.yml`, la ligne `- cron: "*/5 7-16 * * 1-5"` règle la fréquence (5 min est le minimum autorisé par GitHub). Pour ralentir : `*/15` (15 min) ou `*/30` (30 min).

## Limites
Données Yahoo Finance via `yfinance` (non officiel, différé ~15 min, peut parfois échouer). Pas un conseil financier.
