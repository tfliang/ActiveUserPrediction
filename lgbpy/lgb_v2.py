import csv
import datetime
import pandas as pd
import joblib
from lightgbm import LGBMClassifier
from scipy.stats import stats
from sklearn.model_selection import train_test_split, cross_val_score
from skopt import BayesSearchCV
from skopt.callbacks import  DeltaXStopper
from data_process import processing
def select_best_feature(df,y,sorted_feature_name):
    auc_ls = []
    for k in range(8,len(sorted_feature_name),1):
        selected_k_feature = sorted_feature_name[:k]
        print(selected_k_feature)
        # train_set = df[selected_k_feature]
        # train_len = int(len(df[selected_k_feature])*0.75)
        # category_cols = [fea for fea in selected_k_feature if not fea.endswith("bin")]
        # train default classifier
        # categorical_features_indices = [df[selected_k_feature].columns.get_loc(i) for i in category_cols]
        model = LGBMClassifier(n_estimators=200,n_jobs=-1, silent=True, random_state=1234, is_unbalance=True, metric="auc")
        print("begin to evaluate auc of the selected features")
        metrics = cross_val_score(estimator=model,X=df[selected_k_feature].values,y=y.values,scoring="roc_auc",cv=3,n_jobs=-1,verbose=2)
        mean_auc = sum(metrics)/float(len(metrics))
        print((k,mean_auc))
        auc_ls.append((k,mean_auc))
    sorted_ll = sorted(auc_ls,key=lambda x: x[1],reverse=True)
    print(sorted_ll)
    best_k = sorted_ll[0][0]
    print(best_k)
    selected_k_feature = sorted_feature_name[:best_k]
    print(selected_k_feature)
    with open("tencent_stats.csv",'a',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["the selected best k features"])
        writer.writerow(selected_k_feature)
    return selected_k_feature
def predict(clf2, test_set):
    uid = pd.DataFrame()
    # test_set = processing(trainSpan=(1, 30), label=False)
    uid["user_id"] = test_set["user_id"]
    test_set = test_set.drop(labels=["user_id"], axis=1)
    # if isinstance(selector,RFECV):
    #     test_set_new = selector.transform(test_set.values)
    # elif isinstance(selector,list):
    #     test_set_new = test_set[selector]
    # else:
    #     test_set_new = test_set
    print("begin to make predictions")
    res = clf2.predict(test_set.values)
    uid["y_hat"] = pd.Series(res)
    uid["label"] = uid.groupby(by=["user_id"])["y_hat"].transform(lambda x: stats.mode(x)[0][0])
    str_time = str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M"))
    uid_file = "result/uid_" + str_time + ".csv"
    uid.to_csv(uid_file,header=True,index=False)
    active_users = (uid.loc[uid["label"] == 1]).user_id.unique().tolist()
    print(len(active_users))
    print(active_users)
    str_time = str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M"))
    submission_file = "result/submission_" + str_time + ".csv"
    with open(submission_file, "a", newline="") as f:
        writer = csv.writer(f)
        for i in active_users:
            writer.writerow([i])

def run():
    train_set = processing(trainSpan=(1,23),label=True)
    train_label =train_set["label"]
    train_set = train_set.drop(labels=["label","user_id"], axis=1)
    print(train_set.describe())

    train_x, val_x,train_y,val_y = train_test_split(train_set.values,train_label.values,test_size=0.33,random_state=42,shuffle=True)
    print("begin to make prediction with plain features and without tuning parameters")
    initial_params = {
        "n_estimators":400,
        "n_jobs":-1,
        "silent":False,
        "metric":"binary_logloss",
        'max_depth': 8,
        "max_bin": 100,
        "num_leaves": 64,
        'min_child_weight': 0,
        'min_child_samples': 100,
        "min_split_gain": 0.0,
        "learning_rate": 0.02,
        "colsample_bytree": 0.9,
        "subsample": 0.8,
        'reg_alpha': 0.0,
        'reg_lambda': 0.0,
    }
    clf1 = LGBMClassifier(**initial_params)
    clf1.fit(X=train_x,y=train_y,eval_set=(val_x,val_y),early_stopping_rounds=20,eval_metric="auc")
    print("load the test dataset")
    test_set = processing(trainSpan=(1, 30), label=False)
    print("begin to make prediction")
    predict(clf1,test_set)

    str_time = str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M"))
    print("begin to get important features")
    feature_names = train_set.columns
    feature_importances = clf1.feature_importances_
    print(feature_importances)
    print(feature_names)

    with open("kuaishou_stats.csv", 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["feature importance of catboost for tencent-crt", str_time])
        # writer.writerow(eval_metrics)
        feature_score_name = sorted(zip(feature_importances, feature_names), reverse=True)
        for score, name in feature_score_name:
            print('{}: {}'.format(name, score))
            writer.writerow([name, score])
    sorted_feature_name = [name for score, name in feature_score_name]
    print(sorted_feature_name)

    print("begin to select important features")
    selected_k_feature = select_best_feature(train_set,train_label,sorted_feature_name)
    test_feature = ["user_id"]+selected_k_feature

    test_set_new = test_set[test_feature]
    train_set_new = train_set[selected_k_feature]


    print("begin to tune the parameters with the selected feature")
    paramsSpace = {
        "n_estimators": (1600, 3000),
        "max_depth": (3, 16),
        "max_bin": (100, 300),
        "num_leaves": (24, 256),
        "min_child_weight": (1e-3, 1e3, 'log-uniform'),
        "min_child_samples": (16, 256),
        "min_split_gain": (1e-6, 1.0, 'log-uniform'),
        "learning_rate": (1e-6, 1.0, 'log-uniform'),
        "colsample_bytree": (0.6, 1.0, 'uniform'),
        "subsample": (0.6, 1.0, 'uniform'),
        'reg_alpha': (1e-3, 1e3, 'log-uniform'),
        'reg_lambda': (1e-3, 1e3, 'log-uniform'),
        "scale_pos_weight": (0.1, 1.0, 'uniform'),
    }

    def tune_parameter(X, y, clf, params):
        # X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
        gs = BayesSearchCV(
            estimator=clf, search_spaces=params,
            scoring="f1", n_iter=60,optimizer_kwargs={"base_estimator":"GBRT"},
            verbose=2, n_jobs=-1, cv=3, refit=True, random_state=1234
        )
        gs.fit(X, y,callback=DeltaXStopper(0.0000001))
        best_params = gs.best_params_
        best_score = gs.best_score_
        print(best_params)
        print(best_score)
        str_time = str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M"))
        with open("kuaishou_stats.csv", 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["the best params for lightgbm: "])
            for key, value in best_params.items():
                writer.writerow([key, value])
            writer.writerow(["the best score for lightgbm: ", best_score,str_time])
        return gs

    model = LGBMClassifier(**initial_params)
    clf2 = tune_parameter(train_set_new.values,train_label.values,model,paramsSpace)
    print("parameter tuning over, begin to save the model!")
    str_time = str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M"))
    model_name = "lightgbm_" + str_time + ".pkl"
    joblib.dump(clf2, model_name)

    print("begin to process the whole dataset and ready to feed into the fitted model")
    predict(clf2,test_set_new)

if __name__=="__main__":
    run()