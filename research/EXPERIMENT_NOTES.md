# RoadGuard AI experiment verification notes

## Verified from the supplied files

- The saved `roadguard_model.joblib` contains a fitted `RandomForestClassifier`, fitted `StandardScaler`, seven feature names, stored accuracy, and feature importances.
- The scaler's stored means and scales exactly match the scaler fit on the 80% training partition of `datasets/roadguard_realworld_derived.csv` using `train_test_split(test_size=0.2, random_state=42, stratify=y)`.
- Applying the saved model to the corresponding 20% test partition reproduces accuracy 80.5970481%, weighted precision 82.4774019%, weighted recall 80.5970481%, weighted F1 80.9232445%, and the confusion matrix included in README.md.
- The original `datasets/mmc2.csv` is semicolon-delimited and has raw source columns. It is not the model-ready file accepted by the website training function.

## Do not overstate

- The saved model and processed dataset establish the model's training/evaluation relationship, but the supplied project files do not include the complete transformation script or the exact rule used to assign the three `risk_label` classes.
- Do not describe the three labels as observed crash outcomes unless an independent label source verifies that.
- The saved feature importances are Random Forest impurity-based feature importances, not SHAP values.
- The model's classification output is a derived driving-risk category, not a validated prediction of an actual collision.

## Runtime/version note

- The serialized estimator reports scikit-learn 1.9.1. The package therefore pins `scikit-learn==1.9.1` in `requirements.txt` to avoid silently changing predictions when the model is loaded or retrained.
- The analysis runtime available during packaging had scikit-learn 1.8.0. Re-training under that different version produced slightly different predictions; those newly trained metrics were not substituted for the saved paper experiment. The saved 1.9.1 model was evaluated directly and reproduced the reported metrics exactly.
