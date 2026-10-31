import json
def response(helmet='absent',vest='unknown'):
 return json.dumps({'id':'synthetic-response','status':'completed','model':'muse-spark-1.3','usage':{'input_tokens':100,'output_tokens':80},'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps({'helmet':helmet,'vest':vest,'helmet_evidence':'synthetic head evidence','vest_evidence':'synthetic torso evidence'})}]}]}).encode()
