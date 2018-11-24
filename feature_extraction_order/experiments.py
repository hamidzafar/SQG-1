"""The main purpose of this class is to conduct experiments for different models and compare their baselines.

"""

from helper import *
from learning.classifier.naivebayesclassifier import NaiveBayesClassifier as NB
from learning.classifier.svmclassifier import SVMClassifier as SVM
from learning.classifier.logisticregression import LogisticRegressionClassifier as MAXE
from sklearn.metrics import accuracy_score
from prepare_train_test import clean_question
from word_embedding import get_embeddings
from pos import get_feature_precompiled
from tqdm import tqdm


TRAIN_PATH = "data/train.json"
TEST_PATH = "data/test.json"


# Trains a model on questions to predict a KB property
# Takes a model instance
def train_model(model):
    print "Preparing Train/Test data"
    x_train, y_train, x_test, y_test = prep_model_train_test()

    print "Training Model"
    print model.train(x_train, y_train)
    print "Training Done"


# Test a model on questions to predict a KB property
# Takes a model instance
def test_model(model, out=False):
    x_train, y_train, x_test, y_test = prep_model_train_test()
    y_hyp = model.predict(x_test)

    print "Model Accuracy on Testset:", accuracy_score(y_test, y_hyp)

    if out:
        for x, y, z in zip(x_test, y_test, y_hyp):
            print x, y, z


# Takes train/test data for feature extraction.
# Returns train/test in the format for model
def prep_model_train_test():
    train = load_json(TRAIN_PATH)
    test = load_json(TEST_PATH)

    print TRAIN_PATH, TEST_PATH

    train = [[clean_question(row["question"]), row["property"]] for row in train]
    test = [[clean_question(row["question"]), row["property"]] for row in test]

    train_x, train_y = zip(*train)
    test_x, test_y = zip(*test)
    return train_x, train_y, test_x, test_y


# Test WE Accuracy on the Testset
def test_embeddings(path):
    data = load_json(path)
    total = len(data)
    correct = 0
    top_two = 0
    top_three = 0
    result = []

    for row in tqdm(data, desc="Getting WE Accuracy"):
        tmp = {}
        question = row["question"]
        prop = row["property"]
        one_hop = [o.replace("http://dbpedia.org/ontology/", "") for o in row["one_hop_ontologies"]]
        features = get_feature_precompiled(question)["keywords"]
        embeddings_result = get_embeddings(features, one_hop)

        tmp["property"] = prop
        tmp["we_result"] = embeddings_result
        tmp["question"] = question
        result.append(tmp)

        # embeddings_result = get_feature_property(features, one_hop)
        # print question, features, prop, embeddings_result
        if prop == embeddings_result[0]:
            correct += 1

        top_three_embeddings = embeddings_result[2]
        top_three_embeddings = [i[0] for i in top_three_embeddings]
        top_three_embeddings = top_three_embeddings[:3]
        if prop in top_three_embeddings:
            top_three += 1

        top_two_embeddings = top_three_embeddings[:2]
        if prop in top_two_embeddings:
            top_two += 1

    print "Top One:", correct*100/float(total)
    print "Top Two:", top_two*100/float(total)
    print "Top Three:", top_three*100/float(total)

    save_json(result, "out/we_exp_results.json")




# Compares NB Accuracy on Testset vs WE
def experiment_1():
    model = NB("models/NB")
    print model.__class__.__name__
    train_model(model)
    test_model(model)
    test_embeddings("data/test.json")


# Compares SVM Accuracy on Testset vs WE
def experiment_2():
    model = SVM("models/SVM")
    print model.__class__.__name__
    train_model(model)
    test_model(model)
    test_embeddings("data/test.json")


# Compares LogR Accuracy on Testset vs WE
def experiment_3():
    model = MAXE("models/LogR")
    print model.__class__.__name__
    train_model(model)
    test_model(model)
    test_embeddings("data/test.json")


# Compares NB Accuracy on SPECIFIC Testset vs WE
def experiment_4():
    model = NB("models/NB")
    print model.__class__.__name__
    global TRAIN_PATH
    TRAIN_PATH = "data/train_1.json"
    global TEST_PATH
    TEST_PATH = "data/test_1.json"
    train_model(model)
    test_model(model)
    test_embeddings("data/test_1.json")


# Compares SVM Accuracy on SPECIFIC Testset vs WE
# Testset is different from trainingset
def experiment_5():
    model = SVM("models/SVM")
    print model.__class__.__name__
    global TRAIN_PATH
    TRAIN_PATH = "data/train_1.json"
    global TEST_PATH
    TEST_PATH = "data/test_1.json"
    train_model(model)
    test_model(model)
    test_embeddings("data/test_1.json")


def main():
    print "MAIN"
    # experiment_1()
    # experiment_2()
    # experiment_3()
    # experiment_4()
    # experiment_5()

    # model = NB()
    # model.load("models/NB")
    # print model.predict([clean_question("what was back street boys first album")])


if __name__ == '__main__':
    main()
