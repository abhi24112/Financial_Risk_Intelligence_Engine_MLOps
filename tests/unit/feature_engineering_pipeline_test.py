from pipelines.feature_engineering_pipeline import FeatureEngineeringPipeline

df = FeatureEngineeringPipeline().run()
print(df.head())
