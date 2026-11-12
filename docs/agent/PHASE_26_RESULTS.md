# PHASE 26 — Results

Verdict: **PROMISING_BUT_UNCONFIRMED**
Rationale: Accepted orthogonal features improved predictive metrics on multiple targets/folds, but this is not a trading-edge claim and is not production-ready.

Champion: `NO_MODEL` | H13_C: `EXPERIMENTAL` | Production: `WAIT` | Phase25: `NO_NEW_EDGE_FOUND`

## Accepted / rejected features

- Accepted (18): `['rv_6', 'rv_24', 'atr_accel_6', 'vol_persist_12', 'er_20', 'consec_dir', 'ret_ac1_24', 'chop_14', 'dist_prior_high_20_atr', 'dist_prior_low_20_atr', 'wick_reject_up_atr', 'wick_reject_dn_atr', 'fail_break_up', 'fail_break_dn', 'range_compression_6_48', 'h1_atr_pct', 'h1_er_10', 'm5_move_vs_h1_range']`
- Rejected (1): `['range_exp_24']`

## Outcome quality (decision-time OOS indices)

```json
{
  "horizons": {
    "1": {
      "n_eligible": 18234,
      "mfe_buy_mean": 0.49334196429008614,
      "mae_buy_mean": 0.5010972674035974,
      "fav_before_adv_rate": 0.4536930289754823,
      "neither_rate": 0.2864429088515959,
      "fwd_vol_mean": NaN,
      "fwd_ret_buy_mean": 8.956413843876277e-07
    },
    "2": {
      "n_eligible": 18234,
      "mfe_buy_mean": 0.7113960740735842,
      "mae_buy_mean": 0.7206397254175756,
      "fav_before_adv_rate": 0.4538140463371847,
      "neither_rate": 0.09339695075134365,
      "fwd_vol_mean": 0.0,
      "fwd_ret_buy_mean": 1.6004887063523111e-06
    },
    "3": {
      "n_eligible": 18234,
      "mfe_buy_mean": 0.8793179962081772,
      "mae_buy_mean": 0.8920839525545232,
      "fav_before_adv_rate": 0.4536182336182336,
      "neither_rate": 0.03751233958538993,
      "fwd_vol_mean": 0.00043151354895476013,
      "fwd_ret_buy_mean": 2.323470627268557e-06
    },
    "4": {
      "n_eligible": 18234,
      "mfe_buy_mean": 1.022940490604745,
      "mae_buy_mean": 1.0388061247814167,
      "fav_before_adv_rate": 0.45366752260801607,
      "neither_rate": 0.01754963255456839,
      "fwd_vol_mean": 0.0005524080417540519,
      "fwd_ret_buy_mean": 3.10523790434444e-06
    },
    "6": {
      "n_eligible": 18234,
      "mfe_buy_mean": 1.269466419469534,
      "mae_buy_mean": 1.2901441299702587,
      "fav_before_adv_rate": 0.45370421371522995,
      "neither_rate": 0.004332565536909071,
      "fwd_vol_mean": 0.0006430634810570639,
      "fwd_ret_buy_mean": 5.136651438044815e-06
    },
    "8": {
      "n_eligible": 18234,
      "mfe_buy_mean": 1.4820749584063144,
      "mae_buy_mean": 1.5091727361205407,
      "fav_before_adv_rate": 0.4538013623379477,
      "neither_rate": 0.0016452780519907865,
      "fwd_vol_mean": 0.0006820038765596537,
      "fwd_ret_buy_mean": 6.337749491079066e-06
    },
    "12": {
      "n_eligible": 18233,
      "mfe_buy_mean": 1.8500177237092943,
      "mae_buy_mean": 1.8913492407224672,
      "fav_before_adv_rate": 0.4536127722609316,
      "neither_rate": 0.0003290736576537048,
      "fwd_vol_mean": 0.000720071800590634,
      "fwd_ret_buy_mean": 1.022206429688469e-05
    }
  },
  "notes": [
    "MFE/MAE are ATR-normalized price excursions after next-bar entry, not net realized R.",
    "Eligible windows exclude gaps (is_after_gap) and minute gaps > 10.",
    "Favorable-before-adverse uses FAV_ATR=0.5 and ADV_ATR=0.5 on BUY path."
  ]
}
```

## Walk-forward predictive results

### `fwd_vol_12` (regression)
- Folds improved: 3 / 3; all folds: True
- WF1: n_test_base=6078 baseline={'mae': 0.00028758939920400095, 'r2': 0.06859626253434514} | ortho={'mae': 0.00027771834756848516, 'r2': 0.10152325383921923} | improved=True
- WF2: n_test_base=6078 baseline={'mae': 0.0002702018755717974, 'r2': -0.035730050610366826} | ortho={'mae': 0.00025599149133146744, 'r2': 0.03799469463616134} | improved=True
- WF3: n_test_base=6077 baseline={'mae': 0.0002609748644623354, 'r2': 0.11759900995774475} | ortho={'mae': 0.000247657398484188, 'r2': 0.15989556296772667} | improved=True

### `mfe_buy_12_atr` (regression)
- Folds improved: 2 / 3; all folds: False
- WF1: n_test_base=6078 baseline={'mae': 1.2946653900158622, 'r2': 0.011619093853579399} | ortho={'mae': 1.300498331408009, 'r2': 0.010980536041998668} | improved=False
- WF2: n_test_base=6078 baseline={'mae': 1.3075207998900564, 'r2': 0.004402860461386271} | ortho={'mae': 1.3061826060756627, 'r2': 0.005368055042459519} | improved=True
- WF3: n_test_base=6077 baseline={'mae': 1.2203993692928212, 'r2': 0.009760489497683045} | ortho={'mae': 1.2181754630030617, 'r2': 0.017013457701209878} | improved=True

### `mae_buy_12_atr` (regression)
- Folds improved: 2 / 3; all folds: False
- WF1: n_test_base=6078 baseline={'mae': 1.2739416803352335, 'r2': 0.013266764738866899} | ortho={'mae': 1.2798711541967283, 'r2': 0.012660995295002642} | improved=False
- WF2: n_test_base=6078 baseline={'mae': 1.2449744509937626, 'r2': -0.013248758808421357} | ortho={'mae': 1.2347154562716185, 'r2': -0.008762823727590074} | improved=True
- WF3: n_test_base=6077 baseline={'mae': 1.3504618291349384, 'r2': 0.012739406497184746} | ortho={'mae': 1.3480354436204465, 'r2': 0.015776695734405766} | improved=True

### `fwd_ret_buy_6` (regression)
- Folds improved: 1 / 3; all folds: False
- WF1: n_test_base=6078 baseline={'mae': 0.001524031174615151, 'r2': -0.0009230575261747198} | ortho={'mae': 0.0015386302171198193, 'r2': -0.012115795376504757} | improved=False
- WF2: n_test_base=6078 baseline={'mae': 0.0014130802636251837, 'r2': -0.006578865169853287} | ortho={'mae': 0.0014131682198447006, 'r2': -0.0063893621738553286} | improved=False
- WF3: n_test_base=6078 baseline={'mae': 0.0014728296230468467, 'r2': -0.0011146857376160835} | ortho={'mae': 0.001471980292015666, 'r2': 0.0010329547223577595} | improved=True

### `fav_before_adv_buy_12` (classification)
- Folds improved: 0 / 3; all folds: False
- WF1: n_test_base=6076 baseline={'log_loss': 0.6882589927501318, 'accuracy': 0.554312047399605, 'brier': 0.24756119226006837} | ortho={'log_loss': 0.6894352850834458, 'accuracy': 0.5464121132323897, 'brier': 0.2481486827313353} | improved=False
- WF2: n_test_base=6075 baseline={'log_loss': 0.6914246509781539, 'accuracy': 0.528395061728395, 'brier': 0.24913357549199214} | ortho={'log_loss': 0.6915485707591028, 'accuracy': 0.5303703703703704, 'brier': 0.2491974798668907} | improved=False
- WF3: n_test_base=6076 baseline={'log_loss': 0.6874409551600833, 'accuracy': 0.5566161948650428, 'brier': 0.2471570515114092} | ortho={'log_loss': 0.6876282913160109, 'accuracy': 0.5465766951942067, 'brier': 0.2472503075369364} | improved=False

## Safety verification

```json
{
  "holdout_exists_unopened": true,
  "legacy_test_names_not_loaded": true,
  "bundle_holdout_flag_false": true,
  "all_times_le_cutoff": true,
  "broker_orders": true,
  "mt5_connections": true,
  "discord_messages": true,
  "telegram_messages": true,
  "packages_installed": true,
  "oci_provisioned": true,
  "github_push": true,
  "autonomous_retrain": true,
  "production_wait": true,
  "champion_no_model": true,
  "h13c_experimental": true,
  "phase25_verdict_preserved": true,
  "phase16a_21_protected_hashes_match": true,
  "all_pass": true
}
```

## Limitations

- Predictive improvement ≠ trading edge; no strategy promotion from this phase.
- MFE/MAE are not net R after costs.
- VWAP family skipped due to volume validity.
- Single predeclared pass; multiple-testing risk remains for future exploration.
- Incomplete H1 candles never used; H1 features require completed hour.

## Commands

```powershell
cd <repo>
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH='src'
python -m unittest phase26.tests.test_phase26 -v
python -m phase26.run_phase26
```

