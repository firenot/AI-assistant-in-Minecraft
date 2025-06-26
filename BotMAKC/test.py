import re
text="текст (123)(231)"
command=re.findall(r'\(.*?\)', text)
print(command)