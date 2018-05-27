class FormGroupBuilder < ActionView::Helpers::FormBuilder
  def form_group(attribute, &block)
    has_errors = @object.errors.include? attribute

    @template.content_tag(:dl, class: "form-group#{" errored" if has_errors}") do
      if has_errors
        @template.capture(&block) +
          @template.content_tag(:dd, @object.errors.full_messages_for(attribute).to_sentence, class: "error")
      else
        block.call
      end
    end
  end
end
