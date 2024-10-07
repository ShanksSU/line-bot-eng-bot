import os
import csv
import configparser
import json, ssl, urllib.request
import copy
import random
import datetime
import pymongo
import pandas as pd
import re
import requests
import base64
from gtts import gTTS

# set and connect mongodb
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["lineBot"]
mycollection = db["userState"]

# 判斷帳號是否存在
def checkAccountExist(user_id, user_name):
    if mycollection.find_one({"user_id": user_id}) == None:
        # 新增帳號
        data = {
            "user_id": user_id,
            "user_name": user_name,
            "user_state": 0,
            "current_course": 0,
            "chapter": 0,
            "current_question": 0,
            "score": 0,
            'answers': [],
            'words_begin': 0,
            'topic_begin': 0,
            "wrong_questions": [],
            "record": []
        }
        result = mycollection.insert_one(data)

# 判斷並更新使用者課程
def update_user_course(data, query):
    course = ["國文", "英文", "數學"]
    if data in course:
        idx = course.index(data)
        new_values = {"$set": {"current_course": idx}}
        update_document(mycollection, query, new_values)

# 判斷並更新使用者狀態
def update_user_state(data, query):
    if data == "閱讀單字":
        state = 1
    elif data == "測驗":
        state = 2
    new_values = {"$set": {"user_state": state}}
    update_document(mycollection, query, new_values)

# 取得單字
def get_words(word_path):
    try:
        df = pd.read_csv(word_path, encoding='utf-8')

        if df.empty:
            print('No data found.')
        else:
            words = df.values.tolist()
            print('題目已下載完畢！')
            return words
    except Exception as e:
        print(f"Failed to get words from CSV: {str(e)}")

def eng_course(data):
    eng_course = ["形容詞", "動物", "身體部位", "服飾", "食物", "疑問字", "數字", "生活用品", "人們", "地方", "介係詞", "時間", "動詞"]
    if data in eng_course:
        idx = eng_course.index(data)
        return idx
    else:
        return -1

# 回傳單字flex模板
def word_flex(event, user_id, domain, wrong_read, word_template, button_template, words, wrong_questions):
    query = {"user_id": user_id}
    result = mycollection.find_one(query)
    words_begin = result.get("words_begin")

    # 原始json格式
    FlexMessage = word_template
    FlexMessage_button = copy.deepcopy(button_template)    

    FlexMessage_contents = copy.deepcopy(word_template['contents'][0])
    FlexMessage['contents'].clear()
    try:
        if wrong_read:
            # 輸出錯誤題目
            for i in range(len(wrong_questions)):
                FlexMessage_contents['hero']['url'] = f'{domain}/static/image/{words[wrong_questions[i]][3]}'
                FlexMessage_contents['body']['contents'][0]['text'] = words[wrong_questions[i]][0] # 單字
                FlexMessage_contents['body']['contents'][1]['contents'][0]['text'] = words[wrong_questions[i]][1] # KK
                FlexMessage_contents['body']['contents'][2]['text'] = words[wrong_questions[i]][2] # 釋義

                FlexMessage_contents['body']['contents'][3]['contents'][0]['text'] = "例句：" # 句子
                FlexMessage_contents['body']['contents'][3]['contents'][1]['text'] = words[wrong_questions[i]][4] # 句子
                FlexMessage_contents['body']['contents'][3]['contents'][2]['text'] = words[wrong_questions[i]][5] # 句子中文

                FlexMessage_button['footer']['contents'][0]['action']['data'] = f'wrong_words={wrong_questions[i]}'
                FlexMessage_button['footer']['contents'][1]['action']['label'] = '聽單字發音'
                FlexMessage_button['footer']['contents'][1]['action']['data'] = f'words={words[wrong_questions[i]][0]}'

                FlexMessage_contents['footer'] = FlexMessage_button['footer']

                FlexMessage['contents'].append(copy.deepcopy(FlexMessage_contents))
            return FlexMessage
        else:
            del FlexMessage_button['footer']['contents'][1]
            if len(words) >= 10: 
                num = 10
            else:
                num = len(words)
            for i in range(num):
                FlexMessage_contents['hero']['url'] = f'{domain}/static/image/{words[words_begin][3]}'
                FlexMessage_contents['body']['contents'][0]['text'] = words[words_begin][0] # 單字
                FlexMessage_contents['body']['contents'][1]['contents'][0]['text'] = words[words_begin][1] # KK
                FlexMessage_contents['body']['contents'][2]['text'] = words[words_begin][2] # 釋義

                FlexMessage_contents['body']['contents'][3]['contents'][0]['text'] = "例句：" # 句子
                FlexMessage_contents['body']['contents'][3]['contents'][1]['text'] = words[words_begin][4] # 句子
                FlexMessage_contents['body']['contents'][3]['contents'][2]['text'] = words[words_begin][5] # 句子中文

                FlexMessage_button['footer']['contents'][0]['action']['label'] = '聽單字發音'
                FlexMessage_button['footer']['contents'][0]['action']['data'] = f'words={words[words_begin][0]}'

                FlexMessage_contents['footer'] = FlexMessage_button['footer']

                FlexMessage['contents'].append(copy.deepcopy(FlexMessage_contents))
                words_begin += 1

            return FlexMessage
    except Exception as e:
        print(f"Failed: {str(e)}")

# 單字轉換題目(生成題目)
def words_to_quiz(word_path, output_file):
    df = pd.read_csv(word_path, encoding='utf-8')
    questions = []
    print(output_file)
    for index, row in df.iterrows():
        chinese_meaning = row[2]
        english_word = row[0]

        # 從DataFrame中隨機選出其他三個英文單字作為選項
        options = [english_word]
        other_words = df[df[df.columns[0]] != english_word][df.columns[0]].tolist()
        random_options = random.sample(other_words, min(3, len(other_words)))
        options.extend(random_options)

        random.shuffle(options)

        options_indices = [df[df[df.columns[0]] == option].index.values[0] for option in options]

        question = {
            'question': f'以下中文的英文意思是什麼？\n {chinese_meaning}',
            'options1': options[0],
            'options2': options[1],
            'options3': options[2],
            'options4': options[3],
            #'feedback': f'答錯搂！\n答案是 {english_word}。',
            'feedback': f'{english_word}',
            'answer': options.index(english_word) + 1,
            'options1_word_index': options_indices[0],# 7
            'options2_word_index': options_indices[1],# 8
            'options3_word_index': options_indices[2],# 9
            'options4_word_index': options_indices[3]# 10
        }
        questions.append(question)

    quiz_df = pd.DataFrame(questions, columns=['question', 'options1', 'options2', 'options3', 'options4', 'feedback', 'answer', 'options1_word_index', 'options2_word_index', 'options3_word_index', 'options4_word_index'])
    quiz_df.to_csv(output_file, index=False, encoding='utf-8')
    print('已生成測驗題目！')
    return output_file

# 取得測驗問題
def get_questions(topic_path, start_index, num_questions):
    try:
        df = pd.read_csv(topic_path, encoding='utf-8')

        if df.empty:
            print('No data found.')
        else:
            total_questions = len(df)
            # 如果問題佇列載入指定的問題數量，調整 num_questions 為剩餘的問題數量
            if start_index + num_questions - 1 > total_questions:
                num_questions = total_questions - start_index + 1

            # 篩選出從start_index開始的num_questions個題目
            selected_questions = df.iloc[start_index - 1:start_index + num_questions - 1].values.tolist()
            print('已取得測驗題目！')
            return selected_questions

    except Exception as e:
        print(f"Failed to get questions from CSV: {str(e)}")

# 保存作答記錄
def save_answer(user_id, query, chapter, current_question, my_ans):
    print("你媽")

# 記錄錯誤題目
def record_wrong_questions(user_id, query, chapter, questions, current_question, my_ans):
    document = mycollection.find_one({"user_id": user_id, "wrong_questions.chapter": f'{chapter}'})
    topic_num = questions[current_question][6 + questions[current_question][6]]
    if document:
        document["wrong_questions"][0]["topic"].append(topic_num)
        mycollection.update_one(query, {"$set": document})
        print("錯誤題目添加成功")
    else:
        new_data = {
            "chapter": f'{chapter}',
            "topic": [topic_num],
            "index": 0
        }
        result = mycollection.find_one(query)
        wrong_questions = result.get("wrong_questions", [])
        wrong_questions.append(new_data)
        new_values = {"$set": {"wrong_questions": wrong_questions}}
        update_document(mycollection, query, new_values)
        print("錯誤題目集合新建成功")

# 單字轉換語音
def word_to_audio(word, domain, word_audio_path):
    print(word)
    tts=gTTS(text=word, lang='en')
    tts.save(f'.{word_audio_path}')
    url = domain + word_audio_path
    return url

# 寫入CSV檔案
def write_to_csv(data, file_path):
    title = ["題目", "答案", "使否正確", "所選擇選項"]
    with open(file_path, mode='w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(title)
        writer.writerows(data)
    print(f"CSV文件已成功寫入：{file_path}")

# 回傳CSV檔案flex模板
def csv_to_flex(file_path):
    template = json.load(open('flex_message/test.json','r', encoding = 'utf-8'))
    # print(template['body']['contents'][2]['contents'][0]['contents'])
    record_template = copy.deepcopy(template['body']['contents'][2]['contents'][0])

    # 讀取csv檔案
    df = pd.read_csv(file_path)
    record = df.values.tolist()

    for i in range(len(record)):
        match = re.search(r"以下中文的英文意思是什麼？\n (\S+)", record[i][0])
        if match:
            record_template['contents'][0]['text'] = match.group(1)
            record_template['contents'][1]['text'] = record[i][1]
            record_template['contents'][2]['text'] = record[i][2]
            template['body']['contents'][2]['contents'].append(copy.deepcopy(record_template))
    return template
# 更新
def update_document(collection, query, new_values):
    result = collection.update_one(query, new_values)
    return result.modified_count