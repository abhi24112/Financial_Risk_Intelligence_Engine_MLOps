# Feature Engineering Strategy

This document outlines the feature engineering strategy implemented in `pipelines/feature_engineering_pipeline.py`. 

The core objective of our feature engineering is to build a **production-grade, explainable ML Risk Engine**, rather than a brute-force classifier optimized solely for Kaggle leaderboards. Instead of randomly combining hundreds of anonymized variables, we focus on engineering a small set (~20) of highly meaningful **behavioral features**.

By teaching the model the behavioral context behind a transaction (e.g., *"Is this amount normal for this user?"* or *"Are they making unusually frequent transactions?"*), we generate predictions that are both highly accurate and easily explainable to human fraud analysts.

---

## 1. The Temporal Leakage Rule (Critical)

In a real-world production system, a model scoring a transaction at 10:00 AM cannot possibly know about a transaction that will occur at 3:00 PM. 

If we calculate historical averages or frequencies across the *entire* dataset simultaneously, we introduce **temporal leakage**, meaning the model "cheats" by using future data to predict the past.

**Our Solution**: The pipeline forces strict temporal safety.
1. The entire dataset is sorted chronologically by `TransactionDT`.
2. All aggregations use expanding cumulative counts (`cumcount`, `expanding`) or rolling windows (`rolling("24h")`).
3. This guarantees that for any transaction $T$, features are calculated using **only transactions that occurred strictly before $T$**.

---

## 2. Feature Groups & Their Significance

### A. Temporal Features
`TransactionDT` is a relative time variable (elapsed seconds). We extract cyclic temporal patterns from it.
*   **`transaction_hour`**: Fraud often spikes during specific, abnormal local hours (e.g., 3:00 AM).
*   **`transaction_dayofweek` / `is_weekend`**: Transaction volume and fraud risk heavily depend on the day of the week.

### B. Amount Features
*   **`amount_log`**: Transaction amounts have long-tail distributions. Log-transforming (`np.log1p`) helps tree-based models split variances more effectively.
*   **`amount_is_round`**: Fraudulent transactions (or money laundering attempts) frequently involve manually typed, whole-dollar amounts rather than natural cents (e.g., $100.00 vs $103.47).

### C. Behavioral Identities (UIDs)
To understand behavior, we need to track identities. Since we do not have a hard `customer_id`, we synthesize them using strong relational anchors:
*   **`uid_card` (`card1` + `card2`)**: The foundational identity representing a specific payment method.
*   **`uid_card_email`**: Granular identity combining the card and their email domain.
*   **`uid_card_device`**: Granular identity combining the card and the physical device.

### D. Past-Only Behavioral Statistics ⭐⭐⭐
This is the most critical feature group. Instead of asking *"What does this transaction look like?"*, we ask *"How does this transaction compare to this identity's previous behavior?"*
*   **`identity_transaction_count`**: How many times have we seen this card before today? (Tracks loyalty/history).
*   **`identity_avg_amount`**: The historical average spend for this identity.
*   **`amount_vs_identity_avg`**: The current amount divided by the historical average. 
    *   *Explainability value*: This provides the exact narrative for our SHAP explainer: *"Transaction amount is 10x the historical average for this behavioral identity."*

### E. Velocity & Time Features ⭐⭐⭐
Velocity features detect rapid bursts of activity, which are classic signals of automated card-testing or account takeover.
*   **`time_since_last_transaction`**: Seconds elapsed since this identity last transacted. (Very short gaps indicate automated scripts).
*   **`transactions_last_24h`**: Total transaction attempts by this identity in the preceding 24 hours.
*   **`amount_last_24h`**: Total money moved by this identity in the preceding 24 hours.

### F. Novelty (Anomaly) Signals ⭐⭐⭐
These features explicitly flag "first-time" occurrences, which are highly predictive of identity theft or new fraudulent setups.
*   **`is_new_email`**: 1 if this is the first time we have ever seen this email domain associated with this card.
*   **`is_new_device`**: 1 if this is the first time we have ever seen this specific physical device associated with this card.
    *   *Explainability value*: Allows the explainer to state: *"This transaction originated from a device not previously observed with this transaction identity."*

---

## Conclusion
By limiting our feature space to these specific, time-aware behavioral features, we prevent the model from overfitting to noise in anonymized columns (`V`, `C`, `D` features) and instead force it to learn the actual mechanics of transactional risk. This creates a resilient, explainable, and production-ready ML risk engine.
