# Training on Colab, synced back to this repo

Four notebooks, one per stage of work, all under this folder so they travel
with the code they call rather than living only in Drive:

| Notebook | Runs | Needs a GPU runtime? |
|---|---|---|
| `01_data_collection.ipynb` | CHIRPS/GloFAS extraction + EM-DAT flood register merge | No |
| `02_train_lstm_autoencoder.ipynb` | `python -m src.train` | Yes |
| `03_model_selection_classifiers.ipynb` | `python -m src.model_selection` | No (the script pins itself to CPU, see the notebook) |
| `04_threshold_tuning_and_validation.ipynb` | `evaluate_pooled_threshold.py` + `walk_forward_validation.py` | No |

Each notebook clones this repo fresh into the Colab VM, installs
`requirements-colab.txt` (the same as `requirements.txt`, minus
`tensorflow-metal`, which is a macOS-only package and will fail to install on
Colab's Linux runtime), runs the real script from `src/` unchanged, then commits
and pushes whatever it produced to a dedicated `colab-training` branch. You pull
that branch locally to get the results into VS Code, nothing is ever copied by
hand.

## One-time setup

**1. Create a GitHub token scoped to just this repo.**

On GitHub: Settings -> Developer settings -> Personal access tokens ->
Fine-grained tokens -> Generate new token.

- Repository access: "Only select repositories" -> `Real-Time-Flood-Data-Pipeline`
- Permissions: Repository permissions -> **Contents: Read and write** (nothing
  else is needed)
- Set an expiration you're comfortable with; you'll generate a new one when it
  lapses
- Copy the token now, GitHub only shows it once

**2. Add it to Colab as a secret, not a pasted value.**

In any Colab notebook: click the key icon in the left sidebar -> "Add new
secret" -> name it `GITHUB_TOKEN`, paste the value, toggle notebook access on.
Every notebook here reads it with `userdata.get("GITHUB_TOKEN")`, so it is never
typed into a cell or committed anywhere.

**3. Create the `colab-training` branch, once, from your own machine.**

The notebooks clone with `-b colab-training`, which only works once that branch
exists on GitHub. In VS Code's terminal, from the repo root:

```bash
git checkout -b colab-training
git add colab/ requirements-colab.txt
git commit -m "Add Colab training notebooks and Colab requirements"
git push -u origin colab-training
git checkout main   # or back to whatever branch you were on
```

## The loop, after setup

1. Open a notebook (`File -> Open notebook -> GitHub`, paste the repo URL, or
   use a `colab.research.google.com/github/DaniellaWambua/Real-Time-Flood-Data-Pipeline/blob/colab-training/colab/<name>.ipynb`
   link directly).
2. Run it top to bottom. The last cell(s) push the results to `colab-training`.
3. Back in VS Code:
   ```bash
   git checkout colab-training
   git pull
   ```
   Merge or cherry-pick into whatever branch you're actually working on when
   you're ready.

## Why a separate branch, not `main`

Colab's commits are regenerated artefacts (trained weights, result JSON), not
reviewed code changes. Keeping them on their own branch means a Colab run never
silently overwrites whatever branch you happen to have checked out locally, and
you decide when to merge a given training run into your real work.
