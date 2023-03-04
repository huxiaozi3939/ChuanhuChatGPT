import json
import gradio as gr
import openai
import os
import sys
import markdown

f = open('apikey')
apikey = f.readline()
f.close()

my_api_key = apikey    # 在这里输入你的 API 密钥
initial_prompt = "You are a helpful assistant."

if my_api_key == "":
    my_api_key = os.environ.get('my_api_key')

if my_api_key == "empty":
    print("Please give a api key!")
    sys.exit(1)

openai.api_key = my_api_key

def parse_text(text):
    lines = text.split("\n")
    for i,line in enumerate(lines):
        if "```" in line:
            items = line.split('`')
            if items[-1]:
                lines[i] = f'<pre><code class="{items[-1]}">'
            else:
                lines[i] = f'</code></pre>'
        else:
            if i>0:
                line = line.replace("<", "&lt;")
                line = line.replace(">", "&gt;")
                lines[i] = '<br/>'+line.replace(" ", "&nbsp;")
    return "".join(lines)

def get_response(system, context, raw = False):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[system, *context],
    )
    if raw:
        return response
    else:
        statistics = f'本次对话Tokens用量【{response["usage"]["total_tokens"]} / 4096】 （ 提问+上文 {response["usage"]["prompt_tokens"]}，回答 {response["usage"]["completion_tokens"]} ）'
        message = response["choices"][0]["message"]["content"]

        message_with_stats = f'{message}\n\n================\n\n{statistics}'
#         message_with_stats = .markdown(message_with_stats)

        return message, parse_text(message)

def predict(chatbot, input_sentence, system, context):
    if len(input_sentence) == 0:
        return []
    context.append({"role": "user", "content": f"{input_sentence}"})

    message, message_with_stats = get_response(system, context)

    context.append({"role": "assistant", "content": message})

    chatbot.append((input_sentence, message_with_stats))

    return chatbot, context

def retry(chatbot, system, context):
    if len(context) == 0:
        return [], []
    message, message_with_stats = get_response(system, context[:-1])
    context[-1] = {"role": "assistant", "content": message}

    chatbot[-1] = (context[-2]["content"], message_with_stats)
    return chatbot, context

def delete_last_conversation(chatbot, context):
    if len(context) == 0:
        return [], []
    chatbot = chatbot[:-1]
    context = context[:-2]
    return chatbot, context

def reduce_token(chatbot, system, context):
    context.append({"role": "user", "content": "请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。在总结中不要加入这一句话。"})

    response = get_response(system, context, raw=True)

    statistics = f'本次对话Tokens用量【{response["usage"]["completion_tokens"]+12+12+8} / 4096】'
    optmz_str = markdown.markdown( f'好的，我们之前聊了:{response["choices"][0]["message"]["content"]}\n\n================\n\n{statistics}' )
    chatbot.append(("请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。", optmz_str))

    context = []
    context.append({"role": "user", "content": "我们之前聊了什么?"})
    context.append({"role": "assistant", "content": f'我们之前聊了：{response["choices"][0]["message"]["content"]}'})
    return chatbot, context

def save_chat_history(filepath, system, context):
    if filepath == "":
        return
    history = {"system": system, "context": context}
    with open(f"conversation/{filepath}.json", "w") as f:
        json.dump(history, f)

def load_chat_history(fileobj):
    with open(fileobj.name, "r") as f:
        history = json.load(f)
    context = history["context"]
    chathistory = []
    for i in range(0, len(context), 2):
        chathistory.append((parse_text(context[i]["content"]), parse_text(context[i+1]["content"])))
    return chathistory , history["system"], context, history["system"]["content"]

def get_history_names():
    with open("history.json", "r") as f:
        history = json.load(f)
    return list(history.keys())


def reset_state():
    return [], []

def update_system(new_system_prompt):
    return {"role": "system", "content": new_system_prompt}


with gr.Blocks() as demo:
    chatbot = gr.Chatbot().style(color_map=("#1D51EE", "#585A5B"))
    context = gr.State([])
    systemPrompt = gr.State(update_system(initial_prompt))
    topic = gr.State("未命名对话历史记录")

    with gr.Row():
        with gr.Column(scale=12):
            txt = gr.Textbox(show_label=False, placeholder="在这里输入").style(container=False)
        with gr.Column(min_width=50, scale=1):
            submitBtn = gr.Button("🚀", variant="primary")
    with gr.Row():
        emptyBtn = gr.Button("🧹 新的对话")
        retryBtn = gr.Button("🔄 重新生成")
        delLastBtn = gr.Button("🗑️ 删除上条对话")
        reduceTokenBtn = gr.Button("♻️ 总结")

    newSystemPrompt = gr.Textbox(show_label=True, placeholder=f"在这里输入新的System Prompt...", label="更改 System prompt").style(container=True)
    systemPromptDisplay = gr.Textbox(show_label=True, value=initial_prompt, interactive=False, label="目前的 System prompt").style(container=True)
    with gr.Accordion(label="保存/加载对话历史记录(在文本框中输入文件名，点击“保存对话”按钮，历史记录文件会被存储到本地)", open=False):
        with gr.Column():
            with gr.Row():
                with gr.Column(scale=6):
                    saveFileName = gr.Textbox(show_label=True, placeholder=f"在这里输入保存的文件名...", label="保存对话", value="对话历史记录").style(container=True)
                with gr.Column(scale=1):
                    saveBtn = gr.Button("💾 保存对话")
                    uploadBtn = gr.UploadButton("📂 读取对话", file_count="single", file_types=["json"])

    txt.submit(predict, [chatbot, txt, systemPrompt, context], [chatbot, context], show_progress=True)
    txt.submit(lambda :"", None, txt)
    submitBtn.click(predict, [chatbot, txt, systemPrompt, context], [chatbot, context], show_progress=True)
    submitBtn.click(lambda :"", None, txt)
    emptyBtn.click(reset_state, outputs=[chatbot, context])
    newSystemPrompt.submit(update_system, newSystemPrompt, systemPrompt)
    newSystemPrompt.submit(lambda x: x, newSystemPrompt, systemPromptDisplay)
    newSystemPrompt.submit(lambda :"", None, newSystemPrompt)
    retryBtn.click(retry, [chatbot, systemPrompt, context], [chatbot, context], show_progress=True)
    delLastBtn.click(delete_last_conversation, [chatbot, context], [chatbot, context], show_progress=True)
    reduceTokenBtn.click(reduce_token, [chatbot, systemPrompt, context], [chatbot, context], show_progress=True)
    uploadBtn.upload(load_chat_history, uploadBtn, [chatbot, systemPrompt, context, systemPromptDisplay], show_progress=True)
    saveBtn.click(save_chat_history, [saveFileName, systemPrompt, context], None, show_progress=True)


demo.launch(share=False)
