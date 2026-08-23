import json

i=1
with open("prevision_id.json","r+",encoding="utf-8") as g:
    data = json.loads("{}")

with open("meteociel_previsions_urls_codes_postaux.txt","r",encoding="utf-8") as f:
    line = str(f.readline())
    while line or i <=36664:
        if i%1000 == 0:

            line = line.replace(";","/").strip("\n")
            
            tokens = line.split("/")
            code_postal = tokens[-1]
            nom_ville = tokens[-2][:-4].capitalize()
            city_id = tokens[-3]
            clef = f"{nom_ville} ({code_postal})"
            data[clef] = city_id
            print(tokens)
            print(clef)
            print(i)
            
        line = line.replace(";","/").strip("\n")
        
        tokens = line.split("/")
        code_postal = tokens[-1]
        nom_ville = tokens[-2][:-4].title()
        city_id = tokens[-3]
        clef = f"{nom_ville.replace('_','-')} ({code_postal})"
        data[clef] = city_id
        line = str(f.readline())

        i+=1


            
with open("prevision_id.json","w",encoding="utf-8") as g:
    json.dump(data,g,indent=4)
