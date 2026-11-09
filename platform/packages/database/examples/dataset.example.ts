import { connect, disconnect, datasetRepository } from '../src'

async function datasetCrudExample() {
  // const mongoUri = process.env.MONGODB_URI ?? 'mongodb://127.0.0.1:27017/eval_platform'
  const mongoUri = 'mongodb://127.0.0.1:27017/eval_platform'

  await connect(mongoUri)
  console.log('Connected to MongoDB:', mongoUri)

  try {
    // 保证示例可重复执行。
    await datasetRepository.deleteMany({ name: 'Dataset Demo' })

    // 1) 新增
    const createdDataset = await datasetRepository.createDataset({
      name: 'Dataset Demo',
      description: 'A sample dataset for CRUD demo',
    })
    console.log('Create:', {
      id: createdDataset.id,
      name: createdDataset.name,
      description: createdDataset.description,
    })

    // 2) 查询
    const foundById = await datasetRepository.findById(createdDataset.id)
    console.log('Read by id:', foundById?.toObject())

    // 3) 更新
    const updatedDataset = await datasetRepository.updateDataset(createdDataset.id, {
      description: 'Description updated by demo',
    })
    console.log('Update:', updatedDataset?.toObject())

    // 4) 列表 / 分页
    const datasets = await datasetRepository.listDatasets()
    const page = await datasetRepository.pageDatasets({ page: 1, page_size: 10 })
    console.log('List count:', datasets.length)
    console.log('Page result:', {
      total: page.total,
      page: page.page,
      page_size: page.page_size,
      pages: page.pages,
      items: page.items.length,
    })

    // 5) 删除
    // const deleted = await datasetRepository.deleteDataset(createdDataset.id)
    // const afterDelete = await datasetRepository.findById(createdDataset.id)
    // console.log('Delete success:', deleted)
    // console.log('Read after delete:', afterDelete)
  } finally {
    await disconnect()
    console.log('Disconnected from MongoDB')
  }
}

datasetCrudExample().catch((error: unknown) => {
  console.error('CRUD demo failed:', error)
  process.exitCode = 1
})
