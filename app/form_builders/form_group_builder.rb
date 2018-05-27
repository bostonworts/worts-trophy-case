class FormGroupBuilder < ActionView::Helpers::FormBuilder
  def form_group(attribute, &block)
    has_errors = @object.errors.include? attribute

    @template.content_tag(:dl, class: "form-group#{" errored" if has_errors}") do
      output = @template.capture(&block)

      if has_errors
        output + error_message_tag(attribute)
      else
        output
      end
    end
  end

  private

  def error_message_tag(attribute)
    @template.content_tag(:dd, @object.errors.full_messages_for(attribute).to_sentence, class: "error")
  end
end
