/**
 * Codegens API typings
 */
import * as S3 from 'aws-sdk/clients/s3'
import Axios from 'axios'
import 'isomorphic-fetch'
import { chain, keyBy } from 'lodash'
import { seq } from 'promise-seq'
import { buildCsvFromData, getStaticCsvUrl } from '../src/components/DownloadAnalysisLink/BuildAnalysis'
import { CONFIG } from '../src/config/config'
import { DATASETS } from '../src/constants/datasets'
import { Adequacies, Dataset, Method, RepresentativePoint } from '../src/constants/datatypes'
import { State, STATES } from '../src/constants/states'
import {
  getAdequacies, getCensusData, getRepresentativePoints, getStaticAdequacyUrl, getStaticDemographicsUrl, getStaticRPUrl
} from '../src/services/api'
import { getAdequacyMode } from '../src/utils/adequacy'
import { safeDatasetHint } from '../src/utils/formatters'

const METHODS: Method[] = ['driving_time', 'straight_line']

/**
* To push files to S3, you will need 'write' permissions for the bucket you are
* trying to push the files to. This script uses your default $AWS_PROFILE.
* WARNING - Please note that file with the same name will be overriden.
*/
const s3Bucket = 'encompass-public-data'
const s3 = new S3()
const uploadToS3 = true
const cacheUSAWide = false

main()

async function main() {

  console.info('Running cache build...')
  // If you would like to check that the backend is actually configured to
  // cache responses, you can use the two lines of code below.
  // However, we suggest checking the config manually and restart the backend.
  // Just to be safe...
  // if (!CONFIG.cache.enabled) {
  //   throw Error('Caching is not activated in the config file.')
  // }
  await testAPIAccess()
  console.info('Cache Census, Rps, Adequacies and CSVs')
  await cacheData()
}

async function testAPIAccess() {
  let r = await Axios.get('http://localhost:8080/api/available-service-areas/')
  if (r.status !== 200) {
    throw Error('GETting http://localhost:8080/api/available-service-areas/. Is the server running?')
  }
}

function cacheData() {
  return seq(...DATASETS.map(dataset => async () => {
    let states: State[] = dataset.usaWide && cacheUSAWide ? STATES.map(_ => _.shortName as State) : [dataset.state]
    console.log(`Dealing with ${safeDatasetHint(dataset)}...`)
    return seq(...states.map(state => async () => {
      dataset.state = state
      console.log(`  Getting Rps and Census for ${safeDatasetHint(dataset)}`)
      let representativePoints = await getRepresentativePoints({ service_area_ids: dataset.serviceAreaIds })
      let census = await getCensusData({ service_area_ids: dataset.serviceAreaIds })

      let rpParams = { Bucket: s3Bucket, Key: getS3Key(getStaticRPUrl(dataset)) }
      let censusParams = { Bucket: s3Bucket, Key: getS3Key(getStaticDemographicsUrl(dataset)) }

      await uploadIFFNotExists(rpParams, JSON.stringify(representativePoints), 'Rps ' + safeDatasetHint(dataset))
      await uploadIFFNotExists(censusParams, JSON.stringify(census), 'Census ' + safeDatasetHint(dataset))

      console.log(`  Done getting Rps and Census for ${safeDatasetHint(dataset)}`)

      let storeLikeRps = createStoreLikeRps(representativePoints, census)

      return seq(...METHODS.map(method => async () => {
        console.log('  Getting Adequacy and result CSV for ' + safeDatasetHint(dataset) + ' for ' + method)
        let adequacies = await getAdequacies({
          method,
          providers: dataset.providers.map((_, n) => ({ latitude: _.lat, longitude: _.lng, id: n })),
          service_area_ids: dataset.serviceAreaIds,
          dataset_hint: safeDatasetHint(dataset)
        })

        let storeLikeAdequacies = createStoreLikeAdequacies(storeLikeRps, adequacies, method, dataset)

        let CSVResult = buildCsvFromData(
          method, dataset.serviceAreaIds, storeLikeAdequacies, storeLikeRps, true)

        if (adequacies) {
          let adequacyParams = { Bucket: s3Bucket, Key: getS3Key(getStaticAdequacyUrl(dataset, method)) }
          let CSVResultsParams = { Bucket: s3Bucket, Key: getS3Key(getStaticCsvUrl(dataset, method)) }
          await uploadIFFNotExists(adequacyParams, JSON.stringify(adequacies), 'Adequacies ' + safeDatasetHint(dataset))
          await uploadIFFNotExists(CSVResultsParams, JSON.stringify(CSVResult), 'CSV Results ' + safeDatasetHint(dataset))
        }
        console.log('  Done getting Adequacy and result CSV for ' + safeDatasetHint(dataset) + ' for ' + method)
      }))
    }))
  }))
}

function getS3Key(s3URL: string) {
  let s3Key = s3URL.replace(CONFIG.staticAssets.rootUrl, '')
  return s3Key
}

function s3Callback(err: any, data: any) { err ? console.log(JSON.stringify(err) + ' ' + JSON.stringify(data)) : console.log('Success') }

function uploadIFFNotExists(params: S3.HeadObjectRequest, body: string, hint: string, forceS3Upload?: boolean) {
  s3.headObject(params, function (err, _) {
    if (forceS3Upload || err && uploadToS3) {
      console.log(`  Uploading to S3 for ${hint}`)
      params = Object.assign(params, { Body: body, ContentType: 'application/json', ACL: 'public-read' })
      s3.putObject(params, s3Callback)
    } else {
      console.log(`  Object already exists for ${hint}`)
    }
  })
}

function createStoreLikeRps(representativePoints: any, census: any) {
  return representativePoints.map(_ => ({
    ..._,
    population: Number(_.population),
    serviceAreaId: _.service_area_id,
    demographics: census[_.service_area_id]
  }))
}

function createStoreLikeAdequacies(storeLikeRps: RepresentativePoint[], adequacies: any[], method: Method, dataset: Dataset) {
  let hash = keyBy(storeLikeRps, 'id')
  let storeLikeAdequacies: Adequacies = chain(storeLikeRps)
    .map(_ => _.id)
    .zipObject(adequacies)
    .mapValues((_, key) => ({
      adequacyMode: getAdequacyMode(
        _, method, hash[key].serviceAreaId, dataset.serviceAreaIds
      ),
      id: _.id,
      toClosestProvider: _.to_closest_provider,
      closestProvider: dataset.providers[_.closest_providers[0]]
    }))
    .value()
  return storeLikeAdequacies
}
