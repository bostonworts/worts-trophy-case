class Subcategory < ApplicationRecord
  belongs_to :category

  validates :bjcp_id, presence: true
  validates :category, presence: true
  validates :name, presence: true

  def self.sorted
    all.sort_by do |sub|
      if sub.bjcp_id.to_i > 0
        [sub.bjcp_id.to_i, sub.bjcp_id]
      else
        [99, sub.bjcp_id]
      end
    end
  end

  def description
    "#{bjcp_id} - #{name}"
  end
end
