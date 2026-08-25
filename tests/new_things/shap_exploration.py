import pandas as pd
import shap
import xgboost as xgb
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split

# 1. Load a sample dataset
data = load_breast_cancer()
X = pd.DataFrame(data.data, columns=data.feature_names)  # type: ignore
y = data.target  # type: ignore

# 2. Train a simple XGBoost model
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = xgb.XGBClassifier(use_label_encoder=False, eval_metric="logloss")
model.fit(X_train, y_train)

# 3. Initialize SHAP explainer
explainer = shap.TreeExplainer(model)

# 4. Calculate SHAP values for a few samples
shap_values = explainer.shap_values(X_test[:5])

# Summary plot (global feature importance)
shap.summary_plot(shap_values, X_test[:5], feature_names=X.columns)

# Force plot (individual prediction explanation)
# shap.initjs()
# shap.force_plot(explainer.expected_value, shap_values[0,:], X_test.iloc[0,:])
