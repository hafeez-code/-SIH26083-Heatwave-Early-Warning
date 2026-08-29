# SIH26083 Heatwave Early Warning

## v0.12 ML dataset and training foundation

The local SQLite database currently stores Areas, historical weather records,
rule-based heatwave-risk assessments, and forecasts.  The rule assessment is
calculated directly from weather values, so its score and level are not valid
supervised-learning labels and are explicitly rejected by the ML dataset
service.  The tracked local database currently contains no historical rows.

`services.ml_dataset` adapts the v0.11 forecast feature service and selects:
temperature, humidity, wind speed, precipitation, their temperature/humidity
interaction, temperature change, rolling temperature mean/max, and the two
weather indicators.  `area_id` and `forecast_timestamp` are preserved as
metadata and never used as model inputs. Rows with missing selected weather
features are dropped; no weather value is imputed.

An independent, validated outcome column must be provided with each record
before a dataset can be prepared. Rows are ordered by timestamp and split by
whole timestamps into approximately 70% train, 15% validation, and 15% test,
so future timestamps cannot enter fitting. Given legitimate labels,
`services.ml_training` fits either scaled logistic regression (classification)
or scaled ridge regression (regression), with classification or regression
metrics for each split. Its fitted pipeline retains preprocessing for future
inference, but v0.12 writes no model artifact.

This is an engineering foundation only: there is no validated target or
historical data in the current repository, so production supervised training
and claims of predictive accuracy remain blocked.
