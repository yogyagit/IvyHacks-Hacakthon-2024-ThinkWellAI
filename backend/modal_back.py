from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from modal_image import image, stub
from modal import asgi_app, Image, Stub, method, enter, Secret
from modal import Volume
from atlas import AtlasClient
import os


# from langchain_cohere import ChatCohere
# from langchain_community.retrievers import CohereRagRetriever
# from langchain_core.documents import Document
# from langchain_openai import OpenAIEmbeddings
# from langchain_community.document_loaders import DirectoryLoader
# from langchain_community.document_loaders import TextLoader


# from langchain import hub
# from langchain_community.document_loaders import WebBaseLoader
# from langchain_community.vectorstores import Chroma
# from langchain_core.output_parsers import StrOutputParser
# from langchain_core.runnables import RunnablePassthrough
# from langchain_text_splitters import RecursiveCharacterTextSplitter
#from langchain_core.prompts import ChatPromptTemplate

web_app = FastAPI()

volume = Volume.from_name("my-data-volume", create_if_missing=True)
mongoDbClient =  AtlasClient()

@stub.cls(image=image, gpu="T4", container_idle_timeout=300,
          secrets=[Secret.from_name("thinkwell-key")], volumes={'/data': volume},)
class RagChain:
    @enter()
    def enter(self):
        from langchain_community.retrievers import CohereRagRetriever
        from langchain_core.documents import Document
        from langchain_openai import OpenAIEmbeddings
        from langchain_community.document_loaders import DirectoryLoader
        from langchain_community.document_loaders import TextLoader
        from langchain_cohere import CohereEmbeddings

        from langchain import hub
        from langchain_community.document_loaders import WebBaseLoader
        from langchain_community.vectorstores import Chroma
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.runnables import RunnablePassthrough
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import FAISS
        print("Inside start..1")
        self.files_dir = "/data/data"
        self.loader = DirectoryLoader(self.files_dir, glob="**/*.txt", loader_cls=TextLoader)
        print("Inside start..2")
        self.docs = self.loader.load()
        print("Inside start..3..")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        print("Inside start..4")
        self.splits = text_splitter.split_documents(self.docs)
        print("Inside start..5")
        #self.vectorstore = Chroma.from_documents(documents=self.splits, embedding=OpenAIEmbeddings())
        self.vectorstore = FAISS.from_documents(documents=self.splits, embedding= CohereEmbeddings(model="embed-english-light-v3.0"))
        #self.vectorstore = Chroma.from_documents(documents=self.splits, embedding= CohereEmbeddings(model="embed-english-light-v3.0"))
        self.retriever = self.vectorstore.as_retriever(search_type="similarity", search_kwargs={'k': 4})
        self.llm = CohereChatbot()
        print('chatbot created inside ragchain')
         

    @method()
    #def invoke(self, question, prompt , llm, chat_history):
    def invoke(self, question, prompt):
    #def invoke(self, question):
        print("Inside invoke")
        #relevant_docs = self.retriever.search(question, k=5)
        relevant_docs = self.vectorstore.similarity_search(question)
        #formatted_docs = "\n\n".join([doc.content for doc in relevant_docs])
        formatted_docs = "\n\n".join([doc.page_content for doc in relevant_docs])
        full_prompt = prompt.format(context=formatted_docs, question=question)
        #response = llm.chat.remote(message=full_prompt, chat_history=chat_history)

        """
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        rag_chain = (
            {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        return rag_chain.invoke({"question": question})
        """

        #return response
        return full_prompt

@stub.cls(image = image, gpu="T4", container_idle_timeout=300, 
        secrets=[Secret.from_name("thinkwell-key")],)
class CohereChatbot:
    @enter()
    #def start(self, model='command-r', max_tokens=4000, temperature=0.5):
    def enter(self): 
        print('AG>.inside start for coherer chatbot')
        import cohere
        import os
        self.client = cohere.Client(os.environ["COHERE_API_KEY"])
        self.model = 'command-r'
        self.max_tokens = 4000
        self.temperature = 0.5

    @method()
    def chat(self, message, chat_history=[]):
        response = self.client.chat(
            chat_history=chat_history,
            message=message,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        return response.text

llm = CohereChatbot()
print('Noel: llm chatbot init done')
rag_chain = RagChain()
print('Noel: llm init done')

@web_app.post("/process_user_data")
async def process_user_data(request: Request):
    data = await request.json()

    firstname = data.get("firstname")
    lastname = data.get("lastname")
    email = data.get("email")
    user_id = data.get("user_id")
    session_id = mongoDbClient.insert_user_data.remote(database_name = 'ThinkWell_AI', collection_name = 'user_data',user_id = user_id, firstname = firstname, lastname = lastname, email_id = email)
    if session_id > 1:
        return {"user_type": "Returing User", "session": session_id}
    else:
        return {"user_type": "New User", "session": 1}

@web_app.post("/process_input_initial")
async def process_input_route_initial(request: Request):
    intro_message = """
    Hello, I'm Thinkwell, your AI therapist dedicated to assisting you through Cognitive Behavioral Therapy (CBT). CBT is a form of psychotherapy that helps you manage your problems by changing the way you think and behave. It's typically used to treat anxiety, depression, and other conditions by learning practical self-help strategies.

    Today, I'm here to help you explore your thoughts, identify patterns, and provide support as you learn more about CBT and how it can be applied to improve your daily life. To get started, could you please introduce yourself and share why you have decided to seek therapy? What specific issues would you like to address or what goals are you aiming to achieve through our sessions together?

    Remember, this conversation is a safe space, and everything you share will be kept confidential. Let's start this journey together towards a better understanding of your thoughts and feelings.
    """
    return {"response": intro_message}

@web_app.post("/process_input_followup")
async def process_input_route_followup(request: Request):
    data = await request.json()
    user_prompt = data["user_prompt"]
    #chat_history = data.get("chat_history", [])
    chat_history = data.get("transcript", [])
    print("AG: transcript", chat_history)
    print("AG: transcript", type(chat_history))
    
    for message in chat_history:
        if message["role"] == "assistant":
            message["role"] = "CHATBOT"
        if message["role"] == "user":
            message["role"] = "USER"
        try:
            message["message"] = message.pop("content")
        except KeyError:
            # Handle the case where "content" key does not exist
            print("Exception: 'content' key does not exist in message")
    
    print("AG: message", type(message))
    session_id = data["session_id"]
    print(type)
    # Continuing a session
    if session_id >= 1: # YS For testing purposes. Original : session_id == 1 (04/17: 6:55 PM)
        print("Fetching context and generating response using RagChain and CohereChatbot.")
        # Custom prompt that instructs the llm what to do with the fetched context
        custom_prompt = """
        Given the detailed context from the gathered therapy documents and ongoing conversation, please continue the therapy session. 
        Here are some guidelines based on Cognitive Behavioral Therapy (CBT):
        - Understand why the patient has come for therapy and help construct a case.
        - Use the guidelines and techniques of CBT to deepen understanding of the patient's issues.
        - Maintain the flow of conversation, ensuring that all responses are aligned with therapy goals and the patient's needs.
        - Remember, you are an AI therapist named Thinkwell, conducting this session over text. Avoid describing actions or gestures, and focus on verbal communication only.

        Context:
        {{context}}

        Latest query from patient:
        {{question}}

        Please craft a thoughtful response that adheres to the therapeutic principles mentioned, addressing the patient's concerns directly.
        """
        # Use RagChain to fetch context and generate response with the custom prompt
        print(f"chat_history: {chat_history}")
        print(f"user_prompt: {user_prompt}")
        print(f"session_id: {session_id}")
        #llm = CohereChatbot.remote()
        llm1 = CohereChatbot()
        #rag_chain2 = RagChain.remote()
        #response = rag_chain2.invoke.remote(question=user_prompt, prompt=custom_prompt, llm=llm1, chat_history=chat_history)
        full_prompt = rag_chain.invoke.remote(question=user_prompt, prompt=custom_prompt)
        response = llm.chat.remote(message=full_prompt, chat_history=chat_history)
        
        print("Response received from RagChain and CohereChatbot.")
        return {"response": response}
        
    else:
        return {"response": "Session ID not supported or invalid."}
    """
    else:
        response = continue_followup_session(
        user_prompt, transcript, session_results, previous_transcripts
        )
    
    # Send the response back to the frontend
    """

# Define the continue_session_1 function and any other required functions

@web_app.post("/end_session")
async def end_session_route(request: Request):
    data = await request.json()
    transcript = data.get("transcript", [])
    session_id = data.get("session_id")
    user_id = data.get("user_id")

    # Check if transcript and session ID are provided
    if not transcript or session_id is None:
        return {"response": "Missing necessary data (transcript or session ID)."}

    # Use the custom prompt to instruct the LLM to summarize the session and plan next steps
    if session_id == 1:
        custom_prompt = (
            "As an AI therapist named Thinkwell, you have been conducting a session using Cognitive Behavioral Therapy (CBT). "
            "Based on the attached transcript, summarize the key points discussed during the session and suggest a plan for the next sessions. "
            "Ensure to include techniques that might help the patient and any follow-up actions they should consider. "
            "Transcript: '{}'".format(transcript)
        )
        # Generate the concluding statements using CohereChatbot
        response = await llm.chat.remote(message=custom_prompt, chat_history=transcript)
    else:
        return {"response": "Invalid or unsupported session ID."}

    transcript.append({"role": "assistant", "content": response})

    mongoDbClient.insert_documents.remote(database_name = 'ThinkWell_AI', collection_name = 'user_session_transcripts', session_id = session_id, user_id = user_id, session_transcript = transcript)
    
    return {"response": response}

@web_app.post("/logout_session_update")
async def logout_session_update(request: Request):
    data = await request.json()
    transcript = data.get("transcript", [])
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    mongoDbClient.insert_documents.remote(database_name = 'ThinkWell_AI', collection_name = 'user_session_transcripts', session_id = session_id, user_id = user_id, session_transcript = transcript)

@stub.function(image=image, volumes={"/data": volume}, secrets=[Secret.from_name("thinkwell-key")],)
@asgi_app()
def fastapi_app():
    print('Noel: starting fastapi app...')
    return web_app