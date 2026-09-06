with open(r'D:\SIH\VAHANM\docs\00_PROJECT_OVERVIEW.md', 'rb') as f:
    data = f.read()
    for i, b in enumerate(data):
        if b == 0xc2:
            print(f'0xc2 at position {i}')
            start = max(0, i-10)
            end = min(len(data), i+10)
            print(f'Context bytes: {data[start:end]}')
            print(f'Context text (replace errors): {data[start:end].decode("utf-8", errors="replace")}')
            break
