# coding: utf-8

import pandas as pd
import re
import wikipedia
from sklearn import preprocessing
import json
import numpy as np
from gensim.models.doc2vec import LabeledSentence
from gensim.models import Doc2Vec
from nltk.stem.wordnet import WordNetLemmatizer
from sklearn.model_selection import train_test_split
from sklearn.model_selection import GridSearchCV
from sklearn.ensemble import RandomForestClassifier as RFC
from . import rake

stoppath = "Stoplist.txt"
mapping_file = 'mapping.json'
database_file ="content_database.csv"


def TexttoKeywordDataframe(text,class_le):
    #print('Keyword Extraction by NLTK, In Progress...')
    rake_object = rake.Rake(stoppath, 5, 2, 5)
    keywords = rake_object.run(text)
    if len(keywords) == 0:
        print(
            'Hum no keyword find, are you sure it\s an english document ?? Or I cannot understand this document sorry')
        return None
    #remove words with \
    keywords = [i for i in keywords if "\\" not in keywords[0]]
    df = pd.DataFrame(keywords)
    df.pivot(columns=0, values=1)
    df.columns = ['KeyWord', "Score"]
    df["Class_le"]=int(class_le)
    df.Score = df.Score.round(2)
    #print(df)
    return df,keywords

def sampling_class(df, class_col):
    df_tmp = pd.DataFrame()
    len_min = min(df[class_col].value_counts().tolist())
    for c in df[class_col].unique():
        df_tmp = df_tmp.append(df[df[class_col] == c].sample(len_min), ignore_index=True)
    return df_tmp

def split_content(df, content_col, class_col):
  #split each document by sentences
  #TODO need to be defined
    df = pd.concat([pd.Series(row[class_col], row[content_col].split('.'))
               for _, row in df.iterrows()]).reset_index()
    df.columns=[content_col, class_col]
    return df

def CleanWikiPage(content):

    content = re.sub('=.*=', '',content) #remove = sign from title
    content = content.replace(";",'') #delete all ; sign to be sure to not be confuse when saveing df as csv
    content = ''.join(content.splitlines())
    #with open("Output.txt", "w", encoding="utf-8") as text_file:
    #    text_file.write(content)
    return content

def default(o):
    if isinstance(o, np.int64): return int(o)
    raise TypeError

def ConstructDatabaseFromKnwoledgebase(wiki_dico_path):
    df_database = pd.DataFrame(columns=["Content", "Class", "SubClass"])
    json_file = open(wiki_dico_path)  # load knwoledge base
    json_str = json_file.read()
    wiki_dico = json.loads(json_str)
    for key, value in wiki_dico.items():
        for key2, value2 in value.items():
            page = CleanWikiPage(wikipedia.page(pageid=value2).content)
            # add new entry in database
            if key or key2 is '':
                pass
            df_tmp = pd.DataFrame({"Content": page,
                                   "Class": key,
                                   "SubClass": key2}, index=[0])
            df_database = df_database.append(df_tmp, ignore_index=True)
            df_database.reset_index(inplace=True, drop=True)
    le = preprocessing.LabelEncoder()
    le.fit(df_database.Class)
    le_name_mapping = dict(zip(le.classes_, le.transform(le.classes_)))
    with open(mapping_file, 'w') as fp:
        json.dump(le_name_mapping, fp,default=default)
    print(le_name_mapping)
    df_database["Class_le"] = df_database.Class.map(le_name_mapping)
    df_database.to_csv(database_file, header=True, index=False, sep=";")

def label_sentences(df,content_columns="Content",w=None):
    labeled_sentences = []
    for index, datapoint in df.iterrows():
        tokenized_words = re.findall(w, datapoint[content_columns].lower())
        labeled_sentences.append(LabeledSentence(words=tokenized_words, tags=['SENT_%s' % index]))
    return labeled_sentences

def train_doc2vec_model(labeled_sentences):
    model = Doc2Vec(alpha=0.025, min_alpha=0.025)
    model.build_vocab(labeled_sentences)
    for epoch in range(10):
        model.train(labeled_sentences,epochs=model.epochs,total_examples=model.corpus_count)
        model.alpha -= 0.002
        model.min_alpha = model.alpha
    return model

def vectorize_comments(df, d2v_model,df_init,type='Train'):
    y = []
    comments = []
    for i in range(0, df.shape[0]):
        if type == 'Test':
            index = df_init.shape[0]+i-1
        else:
            index = i
        label = 'SENT_%s' % index
        comments.append(d2v_model.docvecs[label])
    df['vectorized_comments'] = comments
    return df

def train_classifier(X,y):
    n_estimators = [100,400]
    min_samples_split = [2]
    min_samples_leaf = [1]
    bootstrap = [True]
    parameters = {'n_estimators': n_estimators, 'min_samples_leaf': min_samples_leaf,
                  'min_samples_split': min_samples_split}
    clf = GridSearchCV(RFC(verbose=1,n_jobs=4), cv=2, param_grid=parameters)
    clf.fit(X, y)
    return clf

def get_df_keyword_from_content(df,content_col,class_col):
    df_k= pd.DataFrame()
    for text in df.groupby([class_col])[content_col]:
        class_le = text[0]
        full_text=''.join(text[1])
        df,keywords = TexttoKeywordDataframe(full_text,class_le)
        df_k = df_k.append(df)
    df_k.to_csv("keywords_database.csv",sep=";",index=False)
    return df_k

def ImportDatabase(content_col="Content", class_col="Class_le",sampling=True,split=True,sort=True):
  df = pd.read_csv(database_file,header=0,sep=";",encoding="utf-8")
  if split:
    df = split_content(df,content_col,class_col)
  if sort:
    df_k = get_df_keyword_from_content(df, content_col,class_col)
  if sampling:
    df = sampling_class(df,class_col)
  if sort:
    for keyword_list in df_k.groupby(class_col)['KeyWord']:
        class_le = keyword_list[0]
        keyword_list = keyword_list[1]
        for index, row in df.iterrows():
            find = False
            if row[class_col] == class_le:
                for keyword in keyword_list :
                    if keyword in row[content_col]:
                        find = True
                if not find:
                    df.drop(index, inplace=True)
  df.reset_index(inplace=True)
  return df
  
def ModelFromDatabase(df, content_col="Content", class_col="Class_le"):
    #Sampling database
    lmtzr = WordNetLemmatizer()
    w = re.compile("\w+", re.I)
    sen = label_sentences(df,content_columns=content_col,w=w)
    model = train_doc2vec_model(sen)
    df = vectorize_comments(df,model,df)
    X_train, X_test, y_train, y_test = train_test_split(df["vectorized_comments"].T.tolist(),
                                                        df[class_col], test_size=0.10, random_state=4)
    classifier = train_classifier(X_train, y_train)
    #print(classifier.predict(X_test))
    print(classifier.score(X_test, y_test))
    return classifier,model,df

def Predict(clf,model,df_init,sentence,content_col='Content'):
    data = {'Content': [sentence]}
    df =  pd.DataFrame(data)
    with open(mapping_file) as f:
        le_name_mapping = json.load(f)
    w = re.compile("\w+", re.I)
    df=df_init.append(df)
    df.reset_index(inplace=True)
    sen = label_sentences(df, content_columns=content_col, w=w)
    model = train_doc2vec_model(sen)
    df = vectorize_comments(df,model,df,type='Train')
    X_test = df["vectorized_comments"].T.tolist()
    X=[]
    X.append(X_test[-1])
    #print(clf.predict(X))
    print(clf.predict_proba(X))
    predicted = clf.predict(X)[0]
    print(predicted)
    with open(mapping_file) as f_in:
       dict_mapping = json.load(f_in)
    for key, value in dict_mapping.items():
      if predicted == value:
        print("I think to  {} % that it is about: {}".format(round(float(clf.predict_proba(X)[0][value])*100,1),key))
        break


