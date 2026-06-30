path = '/opt/ejc/frontend/src/pages/Pecas.tsx'
with open(path) as f:
    src = f.read()

# Move PecaGeneratorModal inside the closing </div>
src = src.replace(
    '    </div>\n\n      <PecaGeneratorModal\n        open={modalIA}\n        onClose={() => setModalIA(false)}\n        onConcluido={(_logId, _doc) => { setModalIA(false); load(); }}\n      />\n  );\n}',
    '      <PecaGeneratorModal\n        open={modalIA}\n        onClose={() => setModalIA(false)}\n        onConcluido={(_logId, _doc) => { setModalIA(false); load(); }}\n      />\n    </div>\n  );\n}',
    1
)

with open(path, 'w') as f:
    f.write(src)
print('OK JSX structure fixed')
