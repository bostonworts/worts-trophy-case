class Subcategory < ApplicationRecord
  belongs_to :category

  validates :bjcp_id, presence: true
  validates :category, presence: true
  validates :name, presence: true

  def description
    "#{bjcp_id} - #{name}"
  end
end
