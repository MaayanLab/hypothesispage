from typing import Union

from fastapi import FastAPI
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

templates = Jinja2Templates(directory="templates")

import s3fs
import h5py as h5
import os
import sys
import numpy as np
import pandas as pd
from tqdm import tqdm
import urllib.request
from scipy import stats
import json
import ssl
import re
import math


ENDPOINT = os.getenv('ENDPOINT', "prismexp")
ENDPOINT_API = os.getenv('ENDPOINT_API', "prismexp")
S3_PREDICTION_URL = os.getenv('S3_PREDICTION_URL', "https://mssm-data.s3.amazonaws.com/px_predictions.2.1.2.h5")

if not os.path.exists("prediction.h5"):
    urllib.request.urlretrieve(S3_PREDICTION_URL, "prediction.h5")

file_path = "prediction.h5"

def load_json(url):
    context = ssl._create_unverified_context()
    req = urllib.request.Request(url)
    r = urllib.request.urlopen(req, context=context).read()
    return(json.loads(r.decode('utf-8')))

enrichr_libraries = load_json("https://maayanlab.cloud/speedrichr/api/listlibs")["library"]

def loadGenesS3(library):
    with h5.File(file_path, 'r') as f:
        return np.array([s.decode("UTF-8") for s in np.array(f[library+"/gene"])])

def loadSetsS3(library):
    with h5.File(file_path, 'r') as f:
        return np.array([s.decode("UTF-8") for s in  np.array(f[library+"/set"])])

def loadGenePredictionS3(library, idx):
    with h5.File(file_path, 'r') as f:
        return stats.zscore(np.array(f[library+"/prediction"][idx, :])[0])

def loadGeneAUCS3(library, idx):
    with h5.File(file_path, 'r') as f:
        return np.float16(f[library+"/auc/gene"][idx])

def loadSetAUCS3(library):
    with h5.File(file_path, 'r') as f:
        return np.array(f[library+"/auc/set"])

def get_predictions(gene_symbol):
    libraries = []
    with h5.File(file_path, 'r') as f:
        libraries = [k for k in f.keys()]
    print(libraries)
    result = {}
    result["gene"] = gene_symbol
    result["predictions"] = {}
    genes = loadGenesS3(libraries[0])
    for lib in libraries:
        sets = loadSetsS3(lib)
        idx = np.where(genes == gene_symbol.upper())[0]
        predictions = loadGenePredictionS3(lib, idx)
        gauc = loadGeneAUCS3(lib, idx)
        sauc = loadSetAUCS3(lib)
        setinfo = []
        for i in range(len(predictions)):
            score = predictions[i]
            term_auc = sauc[i]
            if math.isnan(score):
                score = 0.0
            if math.isnan(term_auc):
                term_auc = 0.0
            # Check if the gene_symbol is in the gold annotations for this term
            is_gold = gene_symbol.upper() in gold_library[lib].get(sets[i], [])
            setinfo.append({
                "term": sets[i],
                "score": float(predictions[i]),
                "term_auc": float(sauc[i]),
                "is_gold": is_gold  # Add gold flag
            })
        setinfo = sorted(setinfo, key=lambda d: d['score'], reverse=True)
        result["predictions"][lib] = {}
        if math.isnan(float(gauc[0])):
            gauc[0] = -1
        result["predictions"][lib]["auc"] = float(gauc[0])
        result["predictions"][lib]["prediction"] = setinfo
    return result

def read_gmt(gmt_file: str):
    url = "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&libraryName="+gmt_file
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        lib = resp.read()
    lines = lib.decode("UTF-8").split("\n")
    library = {}
    for line in lines:
        sp = line.strip().upper().split("\t")
        sp2 = [re.sub(",.*", "",value) for value in sp[2:]]
        sp2 = [x for x in sp2 if x] 
        library[sp[0]] = sp2
    return library

gold_library = {}
allgenes = []
libraries = []
with h5.File(file_path, 'r') as f:
    libraries = [k for k in f.keys()]
for lib in libraries:
    gold_library[lib] = read_gmt(lib)
    allgenes = allgenes+loadGenesS3(lib).tolist()
allgenes = list(set(allgenes))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/"+ENDPOINT_API+"/static", StaticFiles(directory="static"), name="static")

@app.get("/"+ENDPOINT_API, response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.TemplateResponse("main.html", {"request": request, "genes": allgenes, "genesymbol": "", "endpoint": ENDPOINT})

@app.get("/"+ENDPOINT_API+"/g/{gene_symbol}", response_class=HTMLResponse)
async def main_page_gene(request: Request, gene_symbol: str):
    return templates.TemplateResponse("main.html", {"request": request, "genes": allgenes, "genesymbol": gene_symbol, "endpoint": ENDPOINT})

@app.get("/"+ENDPOINT_API+"/workflow", response_class=HTMLResponse)
async def workflow_page(request: Request):
    return templates.TemplateResponse("workflow.html", {"request": request})

@app.get("/"+ENDPOINT_API+"/help", response_class=HTMLResponse)
async def workflow_page(request: Request):
    return templates.TemplateResponse("help.html", {"request": request, "endpoint": ENDPOINT})

@app.get("/"+ENDPOINT_API+"/gene/{gene_symbol}", response_class=HTMLResponse)
async def read_item(request: Request, gene_symbol: str):
    try:
        predictions = get_predictions(gene_symbol)
        return templates.TemplateResponse("gene.html", {"request": request, "gene_symbol": gene_symbol, "predictions": predictions["predictions"], "enrichr_libraries": enrichr_libraries, "gold": gold_library, "endpoint": ENDPOINT})
    except Exception:
        return templates.TemplateResponse("error.html", {"request": request, "gene_symbol": gene_symbol, "endpoint": ENDPOINT})


@app.get("/"+ENDPOINT_API+"/api/v1")
def read_root():
    return {"Hello": "This is the API for the hypothesis page"}

@app.get("/"+ENDPOINT_API+"/api/v1/gene/{gene_symbol}")
def get_gene_predictions(gene_symbol: str):
    try:
        return get_predictions(gene_symbol)
    except Exception:
        return {"error": "gene missing"}

@app.get("/"+ENDPOINT_API+"/api/v1/genes")
def get_genes(gene_symbol: str):
    return allgenes

@app.post("/"+ENDPOINT_API+"/api/v1/texify")
async def postlatex(info : Request):
    data = await info.json()
    print(data)
    return {
        "status" : "SUCCESS",
        "data" : data
    }