// 判断是否为 MongoDB ObjectId (24位十六进制字符串)
export const isObjectId = (str: string): boolean => {
  return /^[0-9a-fA-F]{24}$/.test(str)
}
