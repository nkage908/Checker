# Примеры использования IPTV Checker

## Обработка одного файла
```bash
# Базовая проверка одного файла
python main.py --file playlist.m3u

# С указанием папок для сохранения
python main.py --file playlist.m3u --working-dir ./working --broken-dir ./broken
```

## Обработка папки с файлами
```bash
# Обработка всех M3U файлов в папке
python main.py --dir ./playlists

# С 4 параллельными процессами
python main.py --dir ./playlists --processes 4

# Только рабочие каналы с отдельными папками
python main.py --dir ./playlists --working-only --working-dir ./results/working
```

## Расширенные опции
```bash
# Полная конфигурация
python main.py \
  --dir ./input_playlists \
  --processes 6 \
  --working-dir ./output/working \
  --broken-dir ./output/broken \
  --timeout 15 \
  --concurrent 100 \
  --output-prefix "verified"

# Только сломанные каналы без прогресс-бара
python main.py \
  --dir ./playlists \
  --broken-only \
  --broken-dir ./broken_channels \
  --no-progress
```

## Структура папок
```
project/
├── main.py
├── config.json
├── input_playlists/
│   ├── playlist1.m3u
│   ├── playlist2.m3u8
│   └── playlist3.m3u
├── output/
│   ├── working/
│   │   ├── verified_playlist1_working.m3u
│   │   └── verified_playlist2_working.m3u8
│   └── broken/
│       ├── verified_playlist1_broken.m3u
│       └── verified_playlist2_broken.m3u8
└── logs/
    └── iptv_checker.log
```

## Аргументы командной строки

### Входные данные
- `--file` - путь к одному M3U файлу
- `--dir` - папка с M3U файлами

### Выходные данные  
- `--working-dir` - папка для сохранения рабочих плейлистов
- `--broken-dir` - папка для сохранения сломанных плейлистов
- `--output-prefix` - префикс для выходных файлов

### Производительность
- `--processes` - количество параллельных процессов (по умолчанию 1)
- `--concurrent` - макс. одновременных соединений на процесс
- `--timeout` - таймаут для каждого потока

### Фильтры
- `--working-only` - создать только плейлисты с рабочими каналами
- `--broken-only` - создать только плейлисты со сломанными каналами

### Дополнительно
- `--config` - путь к файлу конфигурации
- `--no-progress` - отключить прогресс-бар