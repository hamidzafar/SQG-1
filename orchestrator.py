from common.graph.graph import Graph
from common.query.querybuilder import QueryBuilder
from parser.lc_quad import LC_Qaud
from sklearn.model_selection import train_test_split
import os
import torch.optim as optim
from learning.treelstm.model import *
from learning.treelstm.vocab import Vocab
from learning.treelstm.trainer import Trainer
from learning.treelstm.dataset import QGDataset
import learning.treelstm.scripts.preprocess_lcquad as preprocess_lcquad
from common.container.uri import Uri
from common.container.linkeditem import LinkedItem
from parser.lc_quad import LC_QaudParser
import common.utility.utility as utility
from learning.classifier.svmclassifier import SVMClassifier
import ujson
import learning.treelstm.Constants as Constants
import numpy as np


class Struct(object): pass


class Orchestrator:
    def __init__(self, logger, question_classifier, double_relation_classifer, parser, auto_train=True):
        self.logger = logger
        self.question_classifier = question_classifier
        self.double_relation_classifer = double_relation_classifer
        self.parser = parser
        self.kb = parser.kb
        self.X_train, self.X_test, self.y_train, self.y_test = [], [], [], []

        if auto_train and not question_classifier.is_trained:
            self.train_question_classifier()

        if auto_train and double_relation_classifer is not None and not double_relation_classifer.is_trained:
            self.train_double_relation_classifier()

        self.dep_tree_cache_file_path = './caches/dep_tree_cache.json'
        if os.path.exists(self.dep_tree_cache_file_path):
            with open(self.dep_tree_cache_file_path) as f:
                self.dep_tree_cache = ujson.load(f)
        else:
            self.dep_tree_cache = dict()

    def prepare_question_classifier_dataset(self, file_path=None):
        if file_path is None:
            ds = LC_Qaud()
        else:
            ds = LC_Qaud(file_path)
        ds.load()
        ds.parse()

        X = []
        y = []
        for qapair in ds.qapairs:
            X.append(qapair.question.text)
            if "COUNT(" in qapair.sparql.raw_query:
                y.append(2)
            elif "ASK WHERE" in qapair.sparql.raw_query:
                y.append(1)
            else:
                y.append(0)

        return X, y

    def prepare_double_relation_classifier_dataset(self, file_path=None):
        if file_path is None:
            ds = LC_Qaud()
        else:
            ds = LC_Qaud(file_path)
        ds.load()
        ds.parse()

        X = []
        y = []
        for qapair in ds.qapairs:
            X.append(qapair.question.text)
            relation_uris = [u for u in qapair.sparql.uris if u.is_ontology() or u.is_type()]
            if len(relation_uris) != len(set(relation_uris)):
                y.append(1)
            else:
                y.append(0)

        return X, y

    def train_question_classifier(self, file_path=None, test_size=0.2):
        X, y = self.prepare_question_classifier_dataset(file_path)
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(X, y, test_size=test_size,
                                                                                random_state=42)
        return self.question_classifier.train(self.X_train, self.y_train)

    def train_double_relation_classifier(self, file_path=None, test_size=0.2):
        X, y = self.prepare_double_relation_classifier_dataset(file_path)
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(X, y, test_size=test_size,
                                                                                random_state=42)
        return self.double_relation_classifer.train(self.X_train, self.y_train)

    def rank(self, args, question, generated_queries):
        if len(generated_queries) == 0:
            return []
        if 2 > 1:
            # try:
            # Load the model
            checkpoint_filename = '%s.pt' % os.path.join(args.save, args.expname)
            dataset_vocab_file = os.path.join(args.data, 'dataset.vocab')
            # metrics = Metrics(args.num_classes)
            vocab = Vocab(filename=dataset_vocab_file,
                          data=[Constants.PAD_WORD, Constants.UNK_WORD, Constants.BOS_WORD, Constants.EOS_WORD])
            similarity = DASimilarity(args.mem_dim, args.hidden_dim, args.num_classes)
            model = SimilarityTreeLSTM(
                vocab.size(),
                args.input_dim,
                args.mem_dim,
                similarity,
                args.sparse)
            criterion = nn.KLDivLoss()
            optimizer = optim.Adagrad(model.parameters(), lr=args.lr, weight_decay=args.wd)
            emb_file = os.path.join(args.data, 'dataset_embed.pth')
            if os.path.isfile(emb_file):
                emb = torch.load(emb_file)
            model.emb.weight.data.copy_(emb)
            checkpoint = torch.load(checkpoint_filename, map_location=lambda storage, loc: storage)
            model.load_state_dict(checkpoint['model'])
            trainer = Trainer(args, model, criterion, optimizer)

            # Prepare the dataset
            json_data = [{"id": "test", "question": question,
                          "generated_queries": [{"query": query["where"], "correct": False} for query in
                                                generated_queries]}]
            output_dir = "./output/tmp"
            preprocess_lcquad.save_split(output_dir, *preprocess_lcquad.split(json_data, self.parser))

            lib_dir = './learning/treelstm/lib/'
            classpath = ':'.join([
                lib_dir,
                os.path.join(lib_dir, 'stanford-parser/stanford-parser.jar'),
                os.path.join(lib_dir, 'stanford-parser/stanford-parser-3.5.1-models.jar')])

            if question in self.dep_tree_cache:
                preprocess_lcquad.parse(output_dir, cp=classpath, dep_parse=False)

                cache_item = self.dep_tree_cache[question]
                with open(os.path.join(output_dir, 'a.parents'), 'w') as f_parent, open(
                        os.path.join(output_dir, 'a.toks'), 'w') as f_token:
                    for i in range(len(generated_queries)):
                        f_token.write(cache_item[0])
                        f_parent.write(cache_item[1])
            else:
                preprocess_lcquad.parse(output_dir, cp=classpath)
                with open(os.path.join(output_dir, 'a.parents')) as f:
                    parents = f.readline()
                with open(os.path.join(output_dir, 'a.toks')) as f:
                    tokens = f.readline()
                self.dep_tree_cache[question] = [tokens, parents]

                with open(self.dep_tree_cache_file_path, 'w') as f:
                    ujson.dump(self.dep_tree_cache, f)
            test_dataset = QGDataset(output_dir, vocab, args.num_classes)

            test_loss, test_pred = trainer.test(test_dataset)
            return test_pred
        # except Exception as expt:
        #     self.logger.error(expt)
        #     return []

    def generate_query(self, question, entities, relations, h1_threshold=None, question_type=None):
        ask_query = False
        sort_query = False
        count_query = False

        if question_type is None:
            question_type = 0
            if self.question_classifier is not None:
                question_type = self.question_classifier.predict([question])
        if question_type == 2:
            count_query = True
        elif question_type == 1:
            ask_query = True

        type_confidence = self.question_classifier.predict_proba([question])[0][question_type]
        if isinstance(self.question_classifier.predict_proba([question])[0][question_type], (np.ndarray, list)):
            type_confidence = type_confidence[0]

        double_relation = False
        # if self.double_relation_classifer is not None:
        #     double_relation = self.double_relation_classifer.predict([question])
        #     if double_relation == 1:
        #         double_relation = True

        graph = Graph(self.kb)
        query_builder = QueryBuilder()
        graph.find_minimal_subgraph(entities, relations, double_relation=double_relation, ask_query=ask_query,
                                    sort_query=sort_query, h1_threshold=h1_threshold)
        valid_walks = query_builder.to_where_statement(graph, self.parser.parse_queryresult, ask_query=ask_query,
                                                       count_query=count_query, sort_query=sort_query)
        # if question_type == 0 and len(relations) == 1:
        #     double_relation = True
        #     graph = Graph(self.kb)
        #     query_builder = QueryBuilder()
        #     graph.find_minimal_subgraph(entities, relations, double_relation=double_relation, ask_query=ask_query,
        #                                 sort_query=sort_query, h1_threshold=h1_threshold)
        #     valid_walks_new = query_builder.to_where_statement(graph, self.parser.parse_queryresult,
        #                                                        ask_query=ask_query,
        #                                                        count_query=count_query, sort_query=sort_query)
        #     valid_walks.extend(valid_walks_new)
        if len(valid_walks) == 0:
            return valid_walks, question_type, 0
        args = Struct()
        base_path = "./learning/treelstm/"
        args.save = os.path.join(base_path, "checkpoints/")
        args.expname = "lc_quad"
        args.mem_dim = 150
        args.hidden_dim = 50
        args.num_classes = 2
        args.input_dim = 300
        args.sparse = False
        args.lr = 0.01
        args.wd = 1e-4
        args.data = os.path.join(base_path, "data/lc_quad/")
        args.cuda = False
        try:
            scores = self.rank(args, question, valid_walks)
        except:
            scores = [1.1 for _ in valid_walks]
        for idx, item in enumerate(valid_walks):
            if idx >= len(scores):
                item["confidence"] = 0.3
            else:
                item["confidence"] = float(scores[idx] - 1)

        return valid_walks, question_type, type_confidence


if __name__ == "__main__":
    args = Struct()
    base_path = "./learning/treelstm/"
    args.save = os.path.join(base_path, "checkpoints/")
    args.expname = "lc_quad"
    args.mem_dim = 150
    args.hidden_dim = 50
    args.num_classes = 2
    args.input_dim = 300
    args.sparse = ""
    args.lr = 0.01
    args.wd = 1e-4
    args.data = os.path.join(base_path, "data/lc_quad/")
    args.cuda = False

    parser = LC_QaudParser()
    kb = parser.kb

    base_dir = "./output"
    question_type_classifier_path = os.path.join(base_dir, "question_type_classifier")
    utility.makedirs(question_type_classifier_path)
    question_type_classifier = SVMClassifier(os.path.join(question_type_classifier_path, "svm.model"))

    o = Orchestrator(None, question_type_classifier, None, parser, True)
    raw_entities = [{"surface": "", "uris": [{"confidence": 1, "uri": "http://dbpedia.org/resource/Bill_Finger"}]}]
    entities = []
    for item in raw_entities:
        uris = [Uri(uri["uri"], kb.parse_uri, uri["confidence"]) for uri in item["uris"]]
        entities.append(LinkedItem(item["surface"], uris))

    raw_relations = [{"surface": "", "uris": [{"confidence": 1, "uri": "http://dbpedia.org/ontology/creator"}]},
                     {"surface": "", "uris": [{"confidence": 1, "uri": "http://dbpedia.org/ontology/ComicsCharacter"}]}]

    relations = []
    for item in raw_relations:
        uris = [Uri(uri["uri"], kb.parse_uri, uri["confidence"]) for uri in item["uris"]]
        relations.append(LinkedItem(item["surface"], uris))

    question = "Which comic characters are painted by Bill Finger?"
    generated_queries = o.generate_query(question, entities, relations)[0]
    # print generated_queries
    # generated_queries = [
    #     {'where': [u'?u_0 <http://dbpedia.org/ontology/creator> <http://dbpedia.org/resource/Bill_Finger>',
    #                u'?u_0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://dbpedia.org/ontology/ComicsCharacter>']},
    #     {'where': [u'?u_0 <http://dbpedia.org/ontology/ComicsCharacter> <http://dbpedia.org/resource/Bill_Finger>',
    #                u'?u_0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://dbpedia.org/ontology/creator>']}
    # ]
    scores = o.rank(args, question, generated_queries)
    print(scores)
    generated_queries.extend(generated_queries)
    scores = o.rank(args, question, generated_queries)
    print(scores)
