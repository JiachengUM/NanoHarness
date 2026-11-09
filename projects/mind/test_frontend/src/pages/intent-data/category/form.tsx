import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/intent'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { useOptions } from '@/hooks/options'

const defaultForm: Category = {}

type Props = {
  formData?: Category
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<Category>(defaultForm)
  const [categoryOptions] = useOptions(Api.category.list, {}, (e) => ({ label: e.name, value: e.id, group: e.group }))
  const groupOptions = useMemo(() => {
    const groups = Array.from(new Set(categoryOptions.map((item) => item.group))).filter((g) => g)
    return [groups.map((g) => ({ label: g, value: g }))]
  }, [categoryOptions])

  const formList: FormItem[] = useMemo(
    () => [
      {
        label: '意图分组',
        name: 'group',
        type: 'autoComplete',
        options: groupOptions,
        required: true,
      },
      {
        label: '意图类别',
        name: 'name',
        type: 'input',
        required: true,
      },
      {
        label: '类别定义',
        name: 'definition',
        type: 'textarea',
        required: true,
      },
      {
        label: '典型正例',
        name: 'example',
        type: 'arrayInput',
        required: true,
      },
      {
        label: '典型负例',
        name: 'example_neg',
        type: 'arrayInput',
      },
      {
        label: '其他注意事项',
        name: 'notice',
        type: 'arrayInput',
      },
    ],
    [groupOptions]
  )

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<Category> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.category.create,
    updateApi: Api.category.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<Category> {...formpProps} />
    </>
  )
}

export default App
