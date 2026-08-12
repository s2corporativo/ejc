import re
src = open('/home/ubuntu/ejc/backend/app/routers/clients.py').read()
# find POST handler and CPF/CNPJ duplicate logic
for m in re.finditer(r'@router\.post\(""\s*,', src):
    start = m.start()
    # print next 120 lines
    print(src[start:start+4500])
    print('===')
    break
