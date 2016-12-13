#!/usr/bin/python
from optparse import OptionParser
#These are the modules that are needed for this script
# module load numpy
# module use /net/gmi.oeaw.ac.at/software/shared/nordborg_common/modulefiles/
# module load pygwas
import logging
import numpy
import numpy.ma
import pandas
from pygwas.core import genotype
import scipy


def likeliTest(n, y):
  p = 0.9999 # This is as close as 1, cannot be 1 because of log
  pS = float(y)/n
  a = y * scipy.log(pS/p)
  b = (n - y) * scipy.log((1-pS)/(1-p))
  return(a+b)

#__________________________________________
inOptions = OptionParser()
inOptions.add_option("-p", "--pos_file", dest="posFile", help="Position file removing the header from VCF", type="string")
inOptions.add_option("-d", "--hdf5_file", dest="hdf5File", help="Path to SNP matrix given in binary hdf5 file", type="string")
inOptions.add_option("-e", "--hdf5_acc_file", dest="hdf5accFile", help="Path to SNP matrix given in binary hdf5 file", type="string")
inOptions.add_option("-o", "--output", dest="outFile", help="Output file with the probability scores", type="string")
inOptions.add_option("-r", "--refScore", dest="refScore", help="Output for refined score", type="string")

(options, args) = inOptions.parse_args()

logging.basicConfig(format='%(levelname)s:%(asctime)s:  %(message)s', level=logging.DEBUG)

GenotypeData = genotype.load_hdf5_genotype_data(options.hdf5File)
GenotypeData_acc = genotype.load_hdf5_genotype_data(options.hdf5accFile)
num_lines = len(GenotypeData.accessions)

# Create a numpy array containing all the positions
logging.info("Reading the position file")
targetSNPs = pandas.read_table(options.posFile, header=None, usecols=[0,1,2])

ScoreList = numpy.zeros(num_lines, dtype="uint32")
NumInfoSites = numpy.zeros(len(GenotypeData.accessions), dtype="uint32")

TotMatchedAccInd = numpy.zeros(0, dtype="uint32")
TotMatchedTarGTs = numpy.zeros(0, dtype="uint32")

NumMatSNPs = 0
chunk_size = 1000

for i in range(1,6):
  perchrTarPos = numpy.where(targetSNPs[0] == i)[0]
  perchrtarSNPpos = numpy.array(targetSNPs[1][perchrTarPos])
  logging.info("Loaded %s chromosome positions from the position file", i)
  start = GenotypeData.chr_regions[i-1][0]
  end = GenotypeData.chr_regions[i-1][1]
  chrpositions = GenotypeData.positions[start:end]
  matchedAccInd = numpy.where(numpy.in1d(chrpositions, perchrtarSNPpos))[0] + start
  matchedTarInd = numpy.where(numpy.in1d(perchrtarSNPpos, chrpositions))[0]
  matchedTarGTs = targetSNPs[2][perchrTarPos[matchedTarInd]]
  TarGTs = numpy.zeros(len(matchedTarGTs), dtype="int8")
  TarGTs[numpy.where(matchedTarGTs != "0/0")[0]] = 1

  NumMatSNPs = NumMatSNPs + len(matchedAccInd)
#  logging.debug("%s", ScoreList)
  for j in range(0, len(matchedAccInd), chunk_size):
    t1001SNPs = GenotypeData.snps[matchedAccInd[j:j+chunk_size],:]
    samSNPs = numpy.reshape(numpy.repeat(TarGTs[j:j+chunk_size], num_lines), (len(TarGTs[j:j+chunk_size]),num_lines))
    ScoreList = ScoreList + numpy.sum(t1001SNPs == samSNPs, axis=0)
    if(len(TarGTs[j:j+chunk_size]) > 1):
      NumInfoSites = NumInfoSites + len(TarGTs[j:j+chunk_size]) - numpy.sum(numpy.ma.masked_less(t1001SNPs, 0).mask.astype(int), axis = 0) # Number of informative sites
    elif(len(TarGTs[j:j+chunk_size]) == 1): 
      NumInfoSites = NumInfoSites + 1 - numpy.ma.masked_less(t1001SNPs, 0).mask.astype(int)
  TotMatchedAccInd = numpy.append(TotMatchedAccInd, matchedAccInd)
  TotMatchedTarGTs = numpy.append(TotMatchedTarGTs, TarGTs)
  logging.info("Done analysing %s positions", NumMatSNPs)

logging.info("Done calculating the scores for each accession")

FinalScore = numpy.zeros(len(GenotypeData.accessions))
FinalScore = [float(ScoreList[i])/float(NumInfoSites[i]) for i in range(len(GenotypeData.accessions))]
LikeLiHoodRatios = [likeliTest(NumInfoSites[i], ScoreList[i]) for i in range(len(GenotypeData.accessions))]
LikeLiHoodRatios = numpy.array(LikeLiHoodRatios).astype("float")

outfile = open(options.outFile, 'w')
for i in range(0, len(GenotypeData.accessions)):
  outfile.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (GenotypeData.accessions[i], int(ScoreList[i]), NumInfoSites[i], FinalScore[i], LikeLiHoodRatios[i], NumMatSNPs))
outfile.close()

TopHitAccs = numpy.where(LikeLiHoodRatios < (min(LikeLiHoodRatios) + 2*numpy.std(LikeLiHoodRatios)))[0]
#TopHitAccs = numpy.sort(numpy.argsort(LikeLiHoodRatios)[0:2])

if len(TopHitAccs) > 1:
  outrefScore=open(options.refScore,'w')
  #Get the positions where the ambiguous acc actually differ
  AccSNPs = GenotypeData_acc.snps[:, TopHitAccs]
  maxi = len(TopHitAccs)
  AccSNPs[AccSNPs == -1] = maxi + 1
  sumNumpy = numpy.sum(AccSNPs, axis = 1)
  RefPosInd = numpy.where((sumNumpy > 0) & (sumNumpy < maxi))[0]
  #This is to get the positions where the access actually differ in
  infoSites = RefPosInd[numpy.in1d(RefPosInd, TotMatchedAccInd)]
  samGTs = TotMatchedTarGTs[numpy.in1d(TotMatchedAccInd, RefPosInd)]
  samSNPs = numpy.reshape(numpy.repeat(samGTs, maxi), (len(samGTs), maxi))
  refScore = numpy.sum(samSNPs == AccSNPs[infoSites,:], axis=0)
  numInfo = len(infoSites)
  refLike = [likeliTest(numInfo, refScore[i]) for i in range(len(TopHitAccs))]
  
  for i in range(0, len(TopHitAccs)):
    outrefScore.write("%s\t%s\t%s\t%s\t%s\n" % (GenotypeData.accessions[TopHitAccs[i]], refScore[i], numInfo, float(refScore[i])/numInfo, refLike[i]))
  outrefScore.close()