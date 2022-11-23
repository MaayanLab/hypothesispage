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


ENDPOINT = os.getenv('ENDPOINT', "hype")
S3_PREDICTION_URL = os.getenv('S3_PREDICTION_URL', "https://mssm-data.s3.amazonaws.com/px_predictions.2.1.2.h5")

if not os.path.exists("prediction.h5"):
    urllib.request.urlretrieve(S3_PREDICTION_URL, "prediction.h5")

file_path = "prediction.h5"

def loadGenesS3(library):
    with h5.File(file_path, 'r') as f:
        return np.array([s.decode("UTF-8") for s in np.array(f[library+"/gene"])])

def loadSetsS3(library):
    with h5.File(file_path, 'r') as f:
        return np.array([s.decode("UTF-8") for s in  np.array(f[library+"/set"])])

def loadGenePredictionS3(library, idx):
    with h5.File(file_path, 'r') as f:
        return np.array(f[library+"/prediction"][idx, :])[0]

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
    for lib in libraries:
        print(lib)
        genes = loadGenesS3(lib)
        sets = loadSetsS3(lib)
        idx = np.where(genes == gene_symbol.upper())[0]
        predictions = loadGenePredictionS3(lib, idx)
        gauc = loadGeneAUCS3(lib, idx)
        sauc = loadSetAUCS3(lib)
        setinfo = []
        for i in range(len(predictions)):
            setinfo.append({"term": sets[i], "score": float(predictions[i]), "term_auc": float(sauc[i])})
        setinfo = sorted(setinfo, key=lambda d: d['score'], reverse=True)
        result["predictions"][lib] = {}
        result["predictions"][lib]["auc"] = float(gauc[0])
        result["predictions"][lib]["prediction"] = setinfo
    return result 
    
allgenes = []
libraries = []
with h5.File(file_path, 'r') as f:
    libraries = [k for k in f.keys()]
for lib in libraries:
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

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/gene/{gene_symbol}", response_class=HTMLResponse)
async def read_item(request: Request, gene_symbol: str):
    predictions = get_predictions(gene_symbol)
    return templates.TemplateResponse("gene.html", {"request": request, "gene_symbol": gene_symbol, "predictions": predictions["predictions"]})

@app.get("/"+ENDPOINT+"/api/v1")
def read_root():
    return {"Hello": "This is the API for the hypothesis page"}

@app.get("/"+ENDPOINT+"/api/v1/gene/{gene_symbol}")
def get_gene_predictions(gene_symbol: str):
    return get_predictions(gene_symbol)

@app.post("/"+ENDPOINT+"/api/v1/texify")
async def postlatex(info : Request):
    data = await info.json()
    print(data)
    
    return {
        "status" : "SUCCESS",
        "data" : data
    }
